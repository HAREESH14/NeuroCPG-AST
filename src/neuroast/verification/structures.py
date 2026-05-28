"""Core data structures for the NeuroAST verification pipeline.

This module defines the language-agnostic intermediate representations and
report models used across the neuro-symbolic verification pipeline. These
Pydantic models serve as the "lingua franca" between C and Java analyses.

Research Contributions Supported:
    - N1 (Deterministic Verification): AlignmentReport provides a mathematical verdict
    - N2 (Hallucination Taxonomy): HallucinationCategory defines structural + semantic + idiom types
    - N4 (Unified IR): ControlFlowGraph abstracts away C/Java differences
    - RC1 (NormPDG): Normalized PDG for cross-language CPG comparison
    - RC5 (Extended Taxonomy): 3-tier hallucination classification
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# Phase 1: Structural (tree-sitter) Models
# =============================================================================


class ControlFlowNodeType(StrEnum):
    """Types of structural elements extracted from source code.

    These are language-agnostic — both C and Java map into these types.
    """

    FUNCTION = "function"
    FOR_LOOP = "for_loop"
    WHILE_LOOP = "while_loop"
    DO_WHILE_LOOP = "do_while_loop"
    IF_BRANCH = "if_branch"
    ELSE_BRANCH = "else_branch"
    SWITCH = "switch"
    CASE = "case"
    RETURN = "return"
    FUNCTION_CALL = "function_call"
    TRY_CATCH = "try_catch"


class ControlFlowNode(BaseModel):
    """A single structural element extracted from source code.

    Represents a node in the control-flow structure of a program. Nodes
    are recursive — a function contains loops, which contain branches, etc.

    Attributes:
        node_type: The type of structural element.
        name: Optional name (function name, called function name, etc.).
        line: Source line number where this element appears.
        children: Nested structural elements (e.g., loops inside a function).
    """

    node_type: ControlFlowNodeType
    name: str | None = None
    line: int
    children: list[ControlFlowNode] = Field(default_factory=list)

    @property
    def depth(self) -> int:
        """Calculate the maximum nesting depth of this node."""
        if not self.children:
            return 0
        return 1 + max(child.depth for child in self.children)

    def count_by_type(self) -> dict[str, int]:
        """Count all descendant nodes grouped by type, including this node."""
        counts: dict[str, int] = {}
        self._count_recursive(counts)
        return counts

    def _count_recursive(self, counts: dict[str, int]) -> None:
        key = self.node_type.value
        counts[key] = counts.get(key, 0) + 1
        for child in self.children:
            child._count_recursive(counts)

    def flatten(self) -> list[ControlFlowNode]:
        """Return all nodes in this subtree as a flat list (pre-order traversal)."""
        result: list[ControlFlowNode] = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


class ControlFlowGraph(BaseModel):
    """The full structural fingerprint of a source file.

    This is the core language-agnostic intermediate representation (N4).
    Both C and Java source files map into this format, enabling
    cross-language structural comparison.

    Attributes:
        language: Source language of this CFG.
        functions: Top-level function/method definitions with their internal structure.
        global_calls: Function calls outside any function definition (e.g., C's main-level calls).
    """

    language: Literal["c", "java"]
    functions: list[ControlFlowNode] = Field(default_factory=list)
    global_calls: list[ControlFlowNode] = Field(default_factory=list)

    def summary(self) -> dict[str, int]:
        """Count all structural elements by type across the entire file.

        Returns a dictionary like:
            {"function": 2, "for_loop": 3, "if_branch": 1, ...}

        This summary is used for the first level of structural comparison
        (global count matching) in the StructuralMatcher.
        """
        counts: dict[str, int] = {}
        for fn in self.functions:
            fn._count_recursive(counts)
        for call in self.global_calls:
            call._count_recursive(counts)
        return counts

    @property
    def total_elements(self) -> int:
        """Total number of structural elements in this CFG."""
        return sum(self.summary().values())


# =============================================================================
# Hallucination Taxonomy (N2 + RC5)
# =============================================================================


class HallucinationCategory(StrEnum):
    """Classification of detected structural/semantic mismatches.

    Three tiers of hallucination classification — this taxonomy is itself
    a research contribution (RC5).

    Structural (Phase 1 — tree-sitter):
        MISSING: Control structure present in source but absent in target.
        INVENTED: Control structure in target that does not exist in source.
        REORDERED: Same structures present but in different order/nesting.
        DEPTH_MISMATCH: Same structures but at different nesting depths.

    Semantic (Phase 2 — Joern CPG):
        BROKEN_DEF_USE: A def→use chain is broken or altered.
        LOST_CONTROL_DEP: A computation is no longer guarded by the correct condition.
        INVALID_TYPE_TRANSFORM: A C type is mapped to an incompatible Java type.
        DATA_FLOW_INVENTION: A new data dependency exists that was not in source.

    Idiom (Phase 2 — tolerated, not hallucinations):
        VALID_API_REPLACE: Structural change preserving semantic equivalence.
        VALID_MEMORY_MODEL: Valid memory model transformation (malloc/free → new/GC).
        VALID_ERROR_HANDLING: Valid error handling idiom change (return -1 → throw).
    """

    # --- Structural (Phase 1) ---
    MISSING = "missing"
    INVENTED = "invented"
    REORDERED = "reordered"
    DEPTH_MISMATCH = "depth_mismatch"

    # --- Semantic (Phase 2) ---
    BROKEN_DEF_USE = "broken_def_use"
    LOST_CONTROL_DEP = "lost_control_dep"
    INVALID_TYPE_TRANSFORM = "invalid_type_transform"
    DATA_FLOW_INVENTION = "data_flow_invention"

    # --- Idiom (Tolerated) ---
    VALID_API_REPLACE = "valid_api_replace"
    VALID_MEMORY_MODEL = "valid_memory_model"
    VALID_ERROR_HANDLING = "valid_error_handling"

    @property
    def is_structural(self) -> bool:
        """Whether this is a Phase 1 structural hallucination."""
        return self in {
            self.MISSING,
            self.INVENTED,
            self.REORDERED,
            self.DEPTH_MISMATCH,
        }

    @property
    def is_semantic(self) -> bool:
        """Whether this is a Phase 2 semantic hallucination."""
        return self in {
            self.BROKEN_DEF_USE,
            self.LOST_CONTROL_DEP,
            self.INVALID_TYPE_TRANSFORM,
            self.DATA_FLOW_INVENTION,
        }

    @property
    def is_idiom(self) -> bool:
        """Whether this is a tolerated idiom transformation (not a hallucination)."""
        return self in {
            self.VALID_API_REPLACE,
            self.VALID_MEMORY_MODEL,
            self.VALID_ERROR_HANDLING,
        }


class HallucinationSeverity(StrEnum):
    """Severity level of a detected hallucination."""

    CRITICAL = "critical"  # Definitely changes program semantics
    WARNING = "warning"  # Likely changes program semantics
    INFO = "info"  # May or may not affect semantics


class Hallucination(BaseModel):
    """A single detected structural or semantic mismatch.

    Each hallucination is classified by category (what kind), severity
    (how bad), and phase (which verification phase detected it). This
    granularity is part of the hallucination taxonomy contribution (N2/RC5).

    Attributes:
        category: The type of hallucination from the 3-tier taxonomy.
        severity: How critical the mismatch is.
        node_type: The structural element type involved (e.g., "for_loop").
        source_location: Where the element appears in source (or "N/A" if invented).
        target_location: Where the element appears in target (or "N/A" if missing).
        description: Human-readable explanation of the mismatch.
        phase_detected: Which verification phase detected this hallucination.
    """

    category: HallucinationCategory
    severity: HallucinationSeverity = HallucinationSeverity.WARNING
    node_type: str
    source_location: str = "N/A"
    target_location: str = "N/A"
    description: str
    phase_detected: Literal["structural", "semantic"] = "structural"


# =============================================================================
# Alignment Reports (N1)
# =============================================================================


class AlignmentReport(BaseModel):
    """The output of any verification phase.

    Provides a deterministic verdict (N1) on whether the source and
    target programs are structurally/semantically aligned. Includes
    detailed hallucination reports and summary statistics.

    Attributes:
        is_aligned: Whether the source and target are aligned.
        hallucinations: List of detected mismatches.
        source_summary: Count of structural elements in source (e.g., {"for_loop": 2}).
        target_summary: Count of structural elements in target.
        confidence: Alignment confidence score (0.0 = completely misaligned, 1.0 = perfect).
        phase: Which verification phase produced this report.
        verification_time_ms: Time taken for verification in milliseconds.
        tree_edit_distance: Zhang-Shasha tree edit distance between CFG trees (Phase 1).
        tree_similarity: Normalized TED similarity: 1 - TED / max(|S|, |T|) (Phase 1).
    """

    is_aligned: bool
    hallucinations: list[Hallucination] = Field(default_factory=list)
    source_summary: dict[str, int] = Field(default_factory=dict)
    target_summary: dict[str, int] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    phase: Literal["structural", "semantic", "progressive"] = "structural"
    verification_time_ms: float = 0.0
    tree_edit_distance: int | None = None
    tree_similarity: float | None = None

    @property
    def structural_hallucinations(self) -> list[Hallucination]:
        """Filter hallucinations detected by Phase 1 (structural)."""
        return [h for h in self.hallucinations if h.category.is_structural]

    @property
    def semantic_hallucinations(self) -> list[Hallucination]:
        """Filter hallucinations detected by Phase 2 (semantic)."""
        return [h for h in self.hallucinations if h.category.is_semantic]

    @property
    def tolerated_idioms(self) -> list[Hallucination]:
        """Filter tolerated idiom transformations (not real hallucinations)."""
        return [h for h in self.hallucinations if h.category.is_idiom]

    def format_for_repair_prompt(self) -> str:
        """Format hallucinations into a string for the LLM repair prompt.

        Returns a numbered list like::

            1. [MISSING] for_loop — The for loop at line 10 is missing.
            2. [INVENTED] try_catch — A try-catch was invented.
        """
        if not self.hallucinations:
            return "No structural issues detected."

        lines: list[str] = []
        for i, h in enumerate(self.hallucinations, 1):
            tag = h.category.value.upper()
            lines.append(f"{i}. [{tag}] {h.node_type} — {h.description}")
        return "\n".join(lines)


# =============================================================================
# Phase 2: Semantic (CPG/PDG) Models — RC1
# =============================================================================


class VariableRole(StrEnum):
    """Normalized role of a variable in the program dependence graph.

    Part of the NormPDG normalization scheme (RC1). Variables are classified
    by their role to enable cross-language comparison where variable names
    and types differ but roles are preserved.
    """

    PARAMETER = "parameter"
    LOCAL = "local"
    RETURN_VALUE = "return_value"
    LOOP_COUNTER = "loop_counter"
    ACCUMULATOR = "accumulator"
    GLOBAL = "global"


class DataDependency(BaseModel):
    """A single def→use chain in the normalized PDG.

    Represents a data dependency: variable V is defined at def_line in
    def_context and used at use_line in use_context. The variable_role
    abstracts away language-specific details (RC1).

    Attributes:
        variable_name: Name of the variable in source code.
        variable_role: Normalized role for cross-language comparison.
        def_context: Where the variable is defined (e.g., "loop_init", "assignment").
        use_context: Where the variable is used (e.g., "loop_condition", "return").
        def_line: Line number of the definition.
        use_line: Line number of the use.
    """

    variable_name: str
    variable_role: VariableRole
    def_context: str
    use_context: str
    def_line: int
    use_line: int


class ControlDependency(BaseModel):
    """A control dependency edge in the normalized PDG.

    Represents the relationship: `dependent_statement` is only executed
    when `condition` evaluates in a certain way. This captures which
    conditions guard which computations (RC2).

    Attributes:
        condition: The predicate expression text.
        dependent_statement: The guarded statement text.
        condition_line: Line number of the condition.
        statement_line: Line number of the dependent statement.
    """

    condition: str
    dependent_statement: str
    condition_line: int
    statement_line: int


class TypeMapping(BaseModel):
    """A C→Java type transformation for validation.

    Used by the semantic matcher to check whether type transformations
    preserve semantics (e.g., int* → int[] is valid, int* → int is not).

    Attributes:
        c_type: The original C type.
        java_type: The translated Java type.
        is_valid: Whether this transformation is semantically valid.
        reason: Explanation of why the transformation is valid/invalid.
    """

    c_type: str
    java_type: str
    is_valid: bool
    reason: str = ""


class NormFunction(BaseModel):
    """A single function's normalized dependency structure.

    Part of the NormPDG (RC1). Captures the semantic essence of a function
    in a language-agnostic format: what data flows where, what conditions
    guard what computations, and what type transformations are involved.

    Attributes:
        name: Function/method name.
        parameters: List of parameter names.
        data_deps: Normalized def→use chains.
        control_deps: Normalized control dependencies.
        type_transforms: C→Java type mappings for validation.
    """

    name: str
    parameters: list[str] = Field(default_factory=list)
    data_deps: list[DataDependency] = Field(default_factory=list)
    control_deps: list[ControlDependency] = Field(default_factory=list)
    type_transforms: list[TypeMapping] = Field(default_factory=list)


class NormPDG(BaseModel):
    """Normalized Program Dependence Graph — language-agnostic (RC1).

    The semantic counterpart of ControlFlowGraph. While ControlFlowGraph
    captures the *shape* of a program (loops, branches, calls), NormPDG
    captures the *meaning* (data flows, control dependencies, type mappings).

    This normalization scheme maps language-specific CPG elements (C pointers,
    Java references, etc.) into a comparable intermediate form. No published
    work has defined such a normalization for CPGs across C and Java.

    Attributes:
        language: Source language of the original CPG.
        functions: Normalized function dependency structures.
    """

    language: Literal["c", "java"]
    functions: list[NormFunction] = Field(default_factory=list)


class ToleratedTransformation(BaseModel):
    """A structural change determined to be a valid idiom, not a hallucination (RC3).

    When Phase 1 flags a structural mismatch (e.g., missing for-loop),
    Phase 2's tolerance engine may determine that the change preserves
    semantics (e.g., for-loop → Arrays.fill()). This record captures
    the initial flag, the tolerance rule applied, and the explanation.

    Attributes:
        original_hallucination: The Phase 1 hallucination that was tolerated.
        tolerance_rule: Name of the tolerance rule that cleared it.
        explanation: Why this transformation preserves semantics.
    """

    original_hallucination: Hallucination
    tolerance_rule: str
    explanation: str


class SemanticAlignmentReport(AlignmentReport):
    """Extended alignment report with semantic hallucination details (RC2+RC3).

    Extends the base AlignmentReport with Phase 2-specific information:
    data-flow preservation, control dependency preservation, type validation,
    and tolerated transformations.

    Attributes:
        data_flow_preserved: Whether all def→use chains are preserved.
        control_deps_preserved: Whether all control dependencies are preserved.
        type_transforms_valid: Whether all C→Java type mappings are valid.
        tolerated_transformations: List of valid idioms that were initially flagged.
        phase1_time_ms: Time spent in Phase 1 (structural) verification.
        phase2_time_ms: Time spent in Phase 2 (semantic) verification.
        data_flow_jaccard: Jaccard similarity J(S_df, T_df) on data-flow edge sets.
        control_dep_jaccard: Jaccard similarity J(S_cd, T_cd) on control-dep edge sets.
        tversky_index: Tversky index T(S, T, α, β) for asymmetric similarity.
    """

    data_flow_preserved: bool = True
    control_deps_preserved: bool = True
    type_transforms_valid: bool = True
    tolerated_transformations: list[ToleratedTransformation] = Field(default_factory=list)
    phase1_time_ms: float = 0.0
    phase2_time_ms: float = 0.0
    data_flow_jaccard: float | None = None
    control_dep_jaccard: float | None = None
    tversky_index: float | None = None


# =============================================================================
# Pipeline Models (N3)
# =============================================================================


class TranslationAttempt(BaseModel):
    """Record of a single translation or repair attempt.

    The pipeline may make multiple attempts (initial translation + repairs).
    Each attempt is recorded for the audit trail, enabling "diminishing
    returns" analysis in the research paper.

    Attributes:
        attempt_number: 1-indexed attempt counter.
        java_code: The Java code produced in this attempt.
        target_cfg: The structural fingerprint of this attempt's Java code.
        alignment_report: The verification result for this attempt.
        repair_prompt: The repair prompt sent to the LLM (None for initial translation).
    """

    attempt_number: int
    java_code: str
    target_cfg: ControlFlowGraph | None = None
    alignment_report: AlignmentReport | None = None
    repair_prompt: str | None = None


class PipelineResult(BaseModel):
    """Final output of the full verification pipeline.

    Captures everything needed for the research evaluation: success/failure,
    all intermediate attempts, timing, and the model used.

    Attributes:
        success: Whether the pipeline produced a verified translation.
        source_code: The original C source code.
        java_code: The final Java translation (best attempt).
        attempts: Number of translation/repair attempts made.
        source_cfg: Structural fingerprint of the source C code.
        final_report: The last alignment report produced.
        attempt_history: Full audit trail of all attempts.
        model: The LLM model used for translation.
        total_time_ms: Total pipeline execution time in milliseconds.
    """

    success: bool
    source_code: str
    java_code: str
    attempts: int
    source_cfg: ControlFlowGraph
    final_report: AlignmentReport
    attempt_history: list[TranslationAttempt] = Field(default_factory=list)
    model: str = ""
    total_time_ms: float = 0.0
