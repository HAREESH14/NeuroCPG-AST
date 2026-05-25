"""
Semantic Matcher — PDG-based hallucination detection (RC2).

Compares two NormPDGs (one from C source, one from Java target) and
detects semantic hallucinations that tree-sitter cannot catch:
  - Broken def→use chains
  - Lost control dependencies
  - Invalid type transformations
  - Invented data-flow dependencies

This module is the core of Research Contribution RC2.
"""

from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher

from neuroast.verification.structures import (
    DataDependency,
    Hallucination,
    HallucinationCategory,
    HallucinationSeverity,
    NormFunction,
    NormPDG,
    SemanticAlignmentReport,
)

logger = logging.getLogger(__name__)


class SemanticMatcher:
    """PDG-based semantic hallucination detection.

    ★ RESEARCH CONTRIBUTION RC2

    Compares two NormPDGs (one from C source, one from Java target) and
    detects semantic mismatches using data-dependency and control-dependency
    analysis.

    Parameters
    ----------
    confidence_threshold:
        Minimum confidence for the report to be marked aligned.
    weights:
        Severity weights for semantic hallucination categories.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.90,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.weights = weights or {
            "broken_def_use": 1.0,
            "lost_control_dep": 0.9,
            "invalid_type_transform": 1.0,
            "data_flow_invention": 0.7,
        }

    def match(
        self,
        source: NormPDG,
        target: NormPDG,
    ) -> SemanticAlignmentReport:
        """Compare two NormPDGs and produce a SemanticAlignmentReport.

        Algorithm:
        1. Align functions by name/position/parameter signature
        2. For each aligned pair:
           a. Compare data dependency chains (def→use preservation)
           b. Compare control dependency trees
           c. Validate type transformations
        3. Classify mismatches using the extended taxonomy

        Parameters
        ----------
        source:
            NormPDG from the original C code.
        target:
            NormPDG from the translated Java code.

        Returns
        -------
        SemanticAlignmentReport
            Detailed semantic verification result.
        """
        start_time = time.perf_counter()
        hallucinations: list[Hallucination] = []

        # 1. Align functions
        aligned_pairs = self._align_functions(source.functions, target.functions)

        # 2. Check each aligned pair
        data_flow_ok = True
        control_deps_ok = True
        types_ok = True

        for s_func, t_func in aligned_pairs:
            # 2a. Data-flow preservation
            df_halls = self._check_data_flow_preservation(s_func, t_func)
            if df_halls:
                data_flow_ok = False
                hallucinations.extend(df_halls)

            # 2b. Control dependency preservation
            cd_halls = self._check_control_dependency_preservation(s_func, t_func)
            if cd_halls:
                control_deps_ok = False
                hallucinations.extend(cd_halls)

            # 2c. Type transformation validation
            tt_halls = self._validate_type_transformations(s_func, t_func)
            if tt_halls:
                types_ok = False
                hallucinations.extend(tt_halls)

        # 3. Handle unmatched functions
        matched_source = {s.name for s, _ in aligned_pairs}
        matched_target = {t.name for _, t in aligned_pairs}

        for s_func in source.functions:
            if s_func.name not in matched_source:
                hallucinations.append(
                    Hallucination(
                        category=HallucinationCategory.MISSING,
                        severity=HallucinationSeverity.CRITICAL,
                        node_type="function",
                        source_location=s_func.name,
                        description=f"Function '{s_func.name}' has no semantic match in target.",
                        phase_detected="semantic",
                    )
                )

        for t_func in target.functions:
            if t_func.name not in matched_target:
                hallucinations.append(
                    Hallucination(
                        category=HallucinationCategory.INVENTED,
                        severity=HallucinationSeverity.WARNING,
                        node_type="function",
                        target_location=t_func.name,
                        description=(
                            f"Function '{t_func.name}' in target has no source counterpart."
                        ),
                        phase_detected="semantic",
                    )
                )

        # Calculate confidence
        total_checks = max(sum(len(s.data_deps) + len(s.control_deps) for s in source.functions), 1)
        weighted_penalty = sum(self.weights.get(h.category.value, 1.0) for h in hallucinations)
        confidence = max(0.0, 1.0 - weighted_penalty / total_checks)
        is_aligned = confidence >= self.confidence_threshold and len(hallucinations) == 0

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return SemanticAlignmentReport(
            is_aligned=is_aligned,
            hallucinations=hallucinations,
            confidence=round(confidence, 4),
            phase="semantic",
            verification_time_ms=elapsed_ms,
            data_flow_preserved=data_flow_ok,
            control_deps_preserved=control_deps_ok,
            type_transforms_valid=types_ok,
            phase2_time_ms=elapsed_ms,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Function Alignment
    # ─────────────────────────────────────────────────────────────────────────

    def _align_functions(
        self,
        source_funcs: list[NormFunction],
        target_funcs: list[NormFunction],
    ) -> list[tuple[NormFunction, NormFunction]]:
        """Align source functions to target functions.

        Strategy:
        1. Exact name match
        2. Fuzzy name match (>70% similarity)
        3. Position-based fallback
        """
        pairs: list[tuple[NormFunction, NormFunction]] = []
        used_targets: set[int] = set()

        # Pass 1: Exact name match
        for s_func in source_funcs:
            for j, t_func in enumerate(target_funcs):
                if j in used_targets:
                    continue
                if s_func.name == t_func.name:
                    pairs.append((s_func, t_func))
                    used_targets.add(j)
                    break

        # Pass 2: Fuzzy name match for remaining
        unmatched_source = [s for s in source_funcs if s.name not in {p[0].name for p in pairs}]
        for s_func in unmatched_source:
            best_score = 0.0
            best_idx = -1
            for j, t_func in enumerate(target_funcs):
                if j in used_targets:
                    continue
                score = SequenceMatcher(None, s_func.name, t_func.name).ratio()
                if score > best_score and score > 0.7:
                    best_score = score
                    best_idx = j

            if best_idx >= 0:
                pairs.append((s_func, target_funcs[best_idx]))
                used_targets.add(best_idx)

        # Pass 3: Position-based fallback for remaining
        remaining_source = [s for s in source_funcs if s.name not in {p[0].name for p in pairs}]
        remaining_target = [(j, t) for j, t in enumerate(target_funcs) if j not in used_targets]
        for s_func, (j, t_func) in zip(remaining_source, remaining_target, strict=False):
            pairs.append((s_func, t_func))
            used_targets.add(j)

        return pairs

    # ─────────────────────────────────────────────────────────────────────────
    # Data-Flow Preservation Check (RC2 core)
    # ─────────────────────────────────────────────────────────────────────────

    def _check_data_flow_preservation(
        self,
        source_fn: NormFunction,
        target_fn: NormFunction,
    ) -> list[Hallucination]:
        """Check that def→use chains are preserved.

        For each data dependency in the source, we check whether a
        corresponding dependency exists in the target with the same
        variable role and compatible def/use contexts.
        """
        hallucinations: list[Hallucination] = []

        # Group source deps by (variable_role, def_context, use_context)
        source_patterns = self._extract_dep_patterns(source_fn.data_deps)
        target_patterns = self._extract_dep_patterns(target_fn.data_deps)

        # Check for missing data dependencies (source has, target doesn't)
        for pattern, s_deps in source_patterns.items():
            t_deps = target_patterns.get(pattern, [])
            if len(t_deps) < len(s_deps):
                missing_count = len(s_deps) - len(t_deps)
                role, def_ctx, use_ctx = pattern
                hallucinations.append(
                    Hallucination(
                        category=HallucinationCategory.BROKEN_DEF_USE,
                        severity=HallucinationSeverity.CRITICAL,
                        node_type="data_dependency",
                        source_location=f"{source_fn.name}",
                        description=(
                            f"In function '{source_fn.name}': {missing_count} "
                            f"def→use chain(s) with role={role}, "
                            f"def_context={def_ctx}, use_context={use_ctx} "
                            f"missing in target."
                        ),
                        phase_detected="semantic",
                    )
                )

        # Check for invented data dependencies (target has, source doesn't)
        for pattern, t_deps in target_patterns.items():
            s_deps = source_patterns.get(pattern, [])
            if len(s_deps) == 0 and len(t_deps) > 0:
                role, def_ctx, use_ctx = pattern
                hallucinations.append(
                    Hallucination(
                        category=HallucinationCategory.DATA_FLOW_INVENTION,
                        severity=HallucinationSeverity.WARNING,
                        node_type="data_dependency",
                        target_location=f"{target_fn.name}",
                        description=(
                            f"In function '{target_fn.name}': {len(t_deps)} "
                            f"invented def→use chain(s) with role={role}, "
                            f"def_context={def_ctx}, use_context={use_ctx}."
                        ),
                        phase_detected="semantic",
                    )
                )

        return hallucinations

    def _extract_dep_patterns(
        self,
        deps: list[DataDependency],
    ) -> dict[tuple[str, str, str], list[DataDependency]]:
        """Group data dependencies by their (role, def_context, use_context) pattern."""
        patterns: dict[tuple[str, str, str], list[DataDependency]] = {}
        for dep in deps:
            key = (dep.variable_role.value, dep.def_context, dep.use_context)
            patterns.setdefault(key, []).append(dep)
        return patterns

    # ─────────────────────────────────────────────────────────────────────────
    # Control Dependency Preservation Check
    # ─────────────────────────────────────────────────────────────────────────

    def _check_control_dependency_preservation(
        self,
        source_fn: NormFunction,
        target_fn: NormFunction,
    ) -> list[Hallucination]:
        """Check that statements are guarded by the same conditions.

        A control dependency hallucination means a computation that was
        conditional in the source is no longer guarded (or vice versa).
        """
        hallucinations: list[Hallucination] = []

        # Simple count-based check for MVP — upgrade to graph comparison later
        source_count = len(source_fn.control_deps)
        target_count = len(target_fn.control_deps)

        if source_count > target_count:
            diff = source_count - target_count
            hallucinations.append(
                Hallucination(
                    category=HallucinationCategory.LOST_CONTROL_DEP,
                    severity=HallucinationSeverity.CRITICAL,
                    node_type="control_dependency",
                    source_location=source_fn.name,
                    description=(
                        f"Function '{source_fn.name}' has {source_count} "
                        f"control dependencies but target '{target_fn.name}' "
                        f"has only {target_count} — {diff} condition guard(s) lost."
                    ),
                    phase_detected="semantic",
                )
            )
        elif target_count > source_count + 1:
            # Allow 1 extra (e.g., added null check) — flag if more
            diff = target_count - source_count
            hallucinations.append(
                Hallucination(
                    category=HallucinationCategory.DATA_FLOW_INVENTION,
                    severity=HallucinationSeverity.INFO,
                    node_type="control_dependency",
                    target_location=target_fn.name,
                    description=(
                        f"Function '{target_fn.name}' has {diff} more "
                        f"control dependencies than source '{source_fn.name}'. "
                        f"These may be valid null checks or invented guards."
                    ),
                    phase_detected="semantic",
                )
            )

        return hallucinations

    # ─────────────────────────────────────────────────────────────────────────
    # Type Transformation Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_type_transformations(
        self,
        source_fn: NormFunction,
        target_fn: NormFunction,
    ) -> list[Hallucination]:
        """Check that C→Java type mappings are semantically valid.

        Uses the type mapping tables from the normalizer module to
        determine whether each transformation preserves semantics.
        """
        hallucinations: list[Hallucination] = []

        # Match source types to target types by variable position
        source_types = {tm.c_type: tm for tm in source_fn.type_transforms if tm.c_type}
        target_types = {tm.java_type: tm for tm in target_fn.type_transforms if tm.java_type}

        # Cross-validate when both source and target have type info
        from neuroast.symbolic.normalizer import validate_type_transform

        for c_type, _s_tm in source_types.items():
            for java_type, _t_tm in target_types.items():
                mapping = validate_type_transform(c_type, java_type)
                if not mapping.is_valid:
                    hallucinations.append(
                        Hallucination(
                            category=HallucinationCategory.INVALID_TYPE_TRANSFORM,
                            severity=HallucinationSeverity.CRITICAL,
                            node_type="type_mapping",
                            source_location=f"{source_fn.name}:{c_type}",
                            target_location=f"{target_fn.name}:{java_type}",
                            description=mapping.reason,
                            phase_detected="semantic",
                        )
                    )

        return hallucinations
