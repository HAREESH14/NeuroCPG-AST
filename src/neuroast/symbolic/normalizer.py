"""
Cross-Language CPG Normalizer — Research Contribution RC1.

Maps language-specific CPG elements into a language-agnostic Normalized
Program Dependence Graph (NormPDG). This normalization scheme is the
foundation of cross-language semantic comparison.

The key insight: C and Java CPGs have fundamentally different node types
(pointer_deref vs field_access, malloc vs new, etc.), but the *roles*
of these operations in the program's data-flow are comparable.

No published work has defined such a normalization for CPGs across C and Java.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from neuroast.symbolic.cpg_extractor import (
    CPGCall,
    CPGControlStructure,
    CPGDataFlowEdge,
    CPGMethod,
    CPGVariable,
    RawCPG,
)
from neuroast.verification.structures import (
    ControlDependency,
    DataDependency,
    NormFunction,
    NormPDG,
    TypeMapping,
    VariableRole,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Normalization Rules (RC1 Core Contribution)
# ─────────────────────────────────────────────────────────────────────────────

# C type → Java type mappings that are semantically valid
VALID_TYPE_TRANSFORMS: dict[str, set[str]] = {
    # Primitive types
    "int": {"int", "Integer", "long", "Long"},
    "long": {"long", "Long", "int", "Integer"},
    "float": {"float", "Float", "double", "Double"},
    "double": {"double", "Double", "float", "Float"},
    "char": {"char", "Character", "String"},
    "void": {"void"},
    "short": {"short", "Short", "int", "Integer"},
    # Pointer types → reference/array types
    "int*": {"int[]", "Integer[]", "List<Integer>"},
    "char*": {"String", "char[]", "StringBuilder", "CharSequence"},
    "float*": {"float[]", "Float[]", "List<Float>"},
    "double*": {"double[]", "Double[]", "List<Double>"},
    "void*": {"Object", "byte[]"},
    # Struct/union → class
    "struct": {"class"},
    # Function pointer → interface/lambda
    "function_pointer": {"Runnable", "Callable", "Function", "interface"},
}

# C memory operations → normalized operations
C_MEMORY_OPS: dict[str, str] = {
    "malloc": "HEAP_ALLOC",
    "calloc": "HEAP_ALLOC",
    "realloc": "HEAP_REALLOC",
    "free": "HEAP_DEALLOC",
}

# Java memory operations → normalized operations
JAVA_MEMORY_OPS: dict[str, str] = {
    "<operator>.alloc": "HEAP_ALLOC",
    # Java has no explicit free — GC handles it
}

# C string functions → Java equivalents (for tolerance matching)
C_STRING_OPS: dict[str, str] = {
    "strcmp": "STRING_COMPARE",
    "strncmp": "STRING_COMPARE",
    "strcpy": "STRING_COPY",
    "strncpy": "STRING_COPY",
    "strcat": "STRING_CONCAT",
    "strncat": "STRING_CONCAT",
    "strlen": "STRING_LENGTH",
    "strstr": "STRING_SEARCH",
    "strchr": "STRING_SEARCH",
    "sprintf": "STRING_FORMAT",
    "snprintf": "STRING_FORMAT",
}

# C I/O functions → normalized I/O operations
C_IO_OPS: dict[str, str] = {
    "printf": "FORMATTED_OUTPUT",
    "fprintf": "FORMATTED_OUTPUT",
    "scanf": "FORMATTED_INPUT",
    "fscanf": "FORMATTED_INPUT",
    "fopen": "FILE_OPEN",
    "fclose": "FILE_CLOSE",
    "fgets": "LINE_READ",
    "fputs": "LINE_WRITE",
    "fread": "BINARY_READ",
    "fwrite": "BINARY_WRITE",
}


class CPGNormalizer:
    """Maps language-specific CPG nodes to NormPDG.

    ★ RESEARCH CONTRIBUTION RC1 — Cross-Language Normalized PDG

    The normalization rules embody semantic knowledge about valid
    cross-language transformations. Getting the mapping wrong creates
    false positives or misses real hallucinations.

    Parameters
    ----------
    language:
        The source language of the CPG being normalized.
    """

    def __init__(self, language: Literal["c", "java"]) -> None:
        self.language = language

    def normalize(self, raw_cpg: RawCPG) -> NormPDG:
        """Normalize a raw CPG into a language-agnostic NormPDG.

        Parameters
        ----------
        raw_cpg:
            The raw CPG from the CPGExtractor.

        Returns
        -------
        NormPDG
            The normalized program dependence graph.
        """
        functions: list[NormFunction] = []

        # Group CPG elements by method
        method_vars = self._group_by_method(raw_cpg)

        for method in raw_cpg.methods:
            if method.is_external:
                continue

            norm_func = self._normalize_function(
                method,
                variables=method_vars.get(method.name, []),
                calls=[c for c in raw_cpg.calls if self._call_in_method(c, method)],
                data_flow=[e for e in raw_cpg.data_flow_edges if e.method_name == method.name],
                control_structures=[
                    cs
                    for cs in raw_cpg.control_structures
                    if self._cs_in_method_range(cs, method, raw_cpg.methods)
                ],
            )
            functions.append(norm_func)

        logger.info(
            "Normalized %d functions from %s CPG",
            len(functions),
            self.language,
        )

        return NormPDG(language=self.language, functions=functions)

    def _normalize_function(
        self,
        method: CPGMethod,
        variables: list[CPGVariable],
        calls: list[CPGCall],
        data_flow: list[CPGDataFlowEdge],
        control_structures: list[CPGControlStructure],
    ) -> NormFunction:
        """Normalize a single function/method."""
        # 1. Normalize data dependencies
        data_deps = self._normalize_data_deps(data_flow, variables, method)

        # 2. Normalize control dependencies
        control_deps = self._normalize_control_deps(control_structures)

        # 3. Extract type mappings (for C functions)
        type_transforms = self._extract_type_mappings(method, variables)

        return NormFunction(
            name=method.name,
            parameters=method.parameters,
            data_deps=data_deps,
            control_deps=control_deps,
            type_transforms=type_transforms,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Data Dependency Normalization
    # ─────────────────────────────────────────────────────────────────────────

    def _normalize_data_deps(
        self,
        data_flow: list[CPGDataFlowEdge],
        variables: list[CPGVariable],
        method: CPGMethod,
    ) -> list[DataDependency]:
        """Convert raw data-flow edges into normalized DataDependency objects."""
        deps: list[DataDependency] = []
        param_names = set(method.parameters)

        for edge in data_flow:
            # Determine variable role
            role = self._infer_variable_role(
                edge.variable, edge.def_code, edge.use_code, param_names
            )

            # Determine def/use contexts
            def_context = self._classify_context(edge.def_code)
            use_context = self._classify_context(edge.use_code)

            deps.append(
                DataDependency(
                    variable_name=edge.variable,
                    variable_role=role,
                    def_context=def_context,
                    use_context=use_context,
                    def_line=edge.def_line,
                    use_line=edge.use_line,
                )
            )

        return deps

    def _infer_variable_role(
        self,
        var_name: str,
        def_code: str,
        use_code: str,
        param_names: set[str],
    ) -> VariableRole:
        """Infer the semantic role of a variable.

        This role-based classification is key to cross-language comparison —
        variable names differ but roles are preserved.
        """
        if var_name in param_names:
            return VariableRole.PARAMETER

        # Loop counter heuristics
        if re.match(r"^[ijk]$", var_name) or "for" in def_code.lower():
            return VariableRole.LOOP_COUNTER

        # Accumulator heuristics (+=, sum, total, count)
        if "+=" in def_code or var_name in ("sum", "total", "count", "result", "acc"):
            return VariableRole.ACCUMULATOR

        # Return value
        if "return" in use_code.lower():
            return VariableRole.RETURN_VALUE

        return VariableRole.LOCAL

    def _classify_context(self, code: str) -> str:
        """Classify what kind of statement a def/use appears in."""
        code_lower = code.lower().strip()

        if code_lower.startswith("for"):
            return "loop_init"
        if code_lower.startswith("while") or code_lower.startswith("do"):
            return "loop_condition"
        if code_lower.startswith("if") or code_lower.startswith("else"):
            return "branch_condition"
        if code_lower.startswith("return"):
            return "return"
        if "+=" in code or "-=" in code or "*=" in code:
            return "accumulation"
        if "=" in code and not ("==" in code or "!=" in code or "<=" in code or ">=" in code):
            return "assignment"
        if "(" in code:
            return "function_call_arg"

        return "other"

    # ─────────────────────────────────────────────────────────────────────────
    # Control Dependency Normalization
    # ─────────────────────────────────────────────────────────────────────────

    def _normalize_control_deps(
        self,
        control_structures: list[CPGControlStructure],
    ) -> list[ControlDependency]:
        """Convert control structures into normalized control dependencies."""
        deps: list[ControlDependency] = []

        for cs in control_structures:
            deps.append(
                ControlDependency(
                    condition=cs.condition or cs.control_structure_type,
                    dependent_statement=cs.code,
                    condition_line=cs.line_number,
                    statement_line=cs.line_number,
                )
            )

        return deps

    # ─────────────────────────────────────────────────────────────────────────
    # Type Mapping Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_type_mappings(
        self,
        method: CPGMethod,
        variables: list[CPGVariable],
    ) -> list[TypeMapping]:
        """Extract type information for later cross-language validation."""
        mappings: list[TypeMapping] = []

        for var in variables:
            if var.type_full_name:
                mappings.append(
                    TypeMapping(
                        c_type=var.type_full_name if self.language == "c" else "",
                        java_type=var.type_full_name if self.language == "java" else "",
                        is_valid=True,  # Validity checked during matching, not extraction
                        reason="extracted from CPG",
                    )
                )

        return mappings

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _group_by_method(self, raw_cpg: RawCPG) -> dict[str, list[CPGVariable]]:
        """Group variables by their containing method (best-effort via line ranges)."""
        result: dict[str, list[CPGVariable]] = {}
        methods_sorted = sorted(
            [m for m in raw_cpg.methods if not m.is_external],
            key=lambda m: m.line_number,
        )

        for var in raw_cpg.variables:
            best_method = ""
            for method in methods_sorted:
                if var.line_number >= method.line_number:
                    best_method = method.name
            if best_method:
                result.setdefault(best_method, []).append(var)

        return result

    def _call_in_method(self, call: CPGCall, method: CPGMethod) -> bool:
        """Check if a call node belongs to a method (heuristic)."""
        return call.line_number >= method.line_number

    def _cs_in_method_range(
        self,
        cs: CPGControlStructure,
        method: CPGMethod,
        all_methods: list[CPGMethod],
    ) -> bool:
        """Check if a control structure is within a method's line range."""
        if cs.line_number < method.line_number:
            return False

        # Find the next method's start line
        next_start = float("inf")
        for m in all_methods:
            if m.line_number > method.line_number and m.line_number < next_start:
                next_start = m.line_number

        return cs.line_number < next_start


def validate_type_transform(c_type: str, java_type: str) -> TypeMapping:
    """Validate whether a C→Java type transformation is semantically valid.

    This is used by the semantic matcher to flag invalid type transforms
    as hallucinations.

    Parameters
    ----------
    c_type:
        The original C type (e.g., ``"int*"``).
    java_type:
        The translated Java type (e.g., ``"int[]"``).

    Returns
    -------
    TypeMapping
        With ``is_valid=True`` if the transform preserves semantics.
    """
    # Normalize C type
    c_norm = c_type.replace(" ", "").lower().rstrip("*").strip()
    c_has_pointer = "*" in c_type

    # Check direct mappings
    lookup_key = f"{c_norm}*" if c_has_pointer else c_norm
    valid_targets = VALID_TYPE_TRANSFORMS.get(lookup_key, set())

    if not valid_targets and "struct" in c_type.lower():
        # Unknown C type — check if it's a struct
        valid_targets = VALID_TYPE_TRANSFORMS.get("struct", set())

    # Normalize Java type for comparison
    java_norm = java_type.strip()

    if java_norm in valid_targets:
        return TypeMapping(
            c_type=c_type,
            java_type=java_type,
            is_valid=True,
            reason=f"Valid mapping: {c_type} → {java_type}",
        )

    # Special case: pointer types should not map to primitives
    if c_has_pointer and java_norm in ("int", "long", "float", "double", "char"):
        return TypeMapping(
            c_type=c_type,
            java_type=java_type,
            is_valid=False,
            reason=f"INVALID: Pointer type {c_type} → primitive {java_type} loses indirection",
        )

    # Default: assume valid for unknown types (conservative)
    return TypeMapping(
        c_type=c_type,
        java_type=java_type,
        is_valid=True,
        reason=f"Unknown mapping — assumed valid: {c_type} → {java_type}",
    )
