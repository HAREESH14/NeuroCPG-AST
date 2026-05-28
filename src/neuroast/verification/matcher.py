"""
Structural matcher — the core research contribution (Pillar N1).

Compares two ControlFlowGraphs (one from C source, one from Java target)
and produces an AlignmentReport with precisely categorised hallucinations.

The matcher is fully deterministic — no LLM is involved.

Algorithm (MVP — 3 levels):
    1. Global count comparison
    2. Function-level alignment (by position, then by name similarity)
    3. Per-function structural diff (loop counts, branch counts, nesting depth)
"""

from __future__ import annotations

import logging
from typing import Literal

from zss import simple_distance
from zss import Node as ZssNode

from neuroast.symbolic.extractor import StructuralExtractor
from neuroast.verification.base import BaseVerifier
from neuroast.verification.structures import (
    AlignmentReport,
    ControlFlowGraph,
    ControlFlowNode,
    Hallucination,
    HallucinationCategory,
    HallucinationSeverity,
)

logger = logging.getLogger(__name__)


class StructuralMatcher:
    """
    Compares source and target ControlFlowGraphs to detect hallucinations.

    This is a pure, deterministic comparison — no LLM, no heuristics,
    just counting and tree comparison.

    Parameters
    ----------
    confidence_threshold:
        Minimum confidence score for the report to be marked ``is_aligned=True``.
    weights:
        Severity weights for each hallucination category (string key → float).
    """

    def __init__(
        self,
        confidence_threshold: float = 0.95,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.weights = weights or {
            "missing": 1.0,
            "invented": 0.8,
            "reordered": 0.3,
            "depth_mismatch": 0.5,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Zhang-Shasha Tree Edit Distance (research-level metric)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _cfn_to_zss(node: ControlFlowNode) -> ZssNode:
        """Convert a ControlFlowNode tree to a zss.Node tree for TED computation.

        Each node is labeled with its type (e.g., 'for_loop', 'if_branch').
        The tree structure is preserved recursively.
        """
        zss_node = ZssNode(node.node_type.value)
        for child in node.children:
            zss_node.addkid(StructuralMatcher._cfn_to_zss(child))
        return zss_node

    def _compute_tree_edit_distance(
        self,
        source_funcs: list[ControlFlowNode],
        target_funcs: list[ControlFlowNode],
    ) -> tuple[int, float]:
        """Compute Zhang-Shasha tree edit distance between two CFG forests.

        Constructs a synthetic root over all function-level trees and
        computes the exact tree edit distance using the Zhang-Shasha (1989)
        algorithm.  Returns both the raw distance and the normalized
        similarity score.

        Returns
        -------
        tuple[int, float]
            (edit_distance, tree_similarity) where tree_similarity
            = 1 - edit_distance / max(|source_nodes|, |target_nodes|, 1).
        """
        # Build synthetic root nodes to handle multi-function files
        s_root = ZssNode("root")
        for fn in source_funcs:
            s_root.addkid(self._cfn_to_zss(fn))

        t_root = ZssNode("root")
        for fn in target_funcs:
            t_root.addkid(self._cfn_to_zss(fn))

        # Count total nodes for normalization
        source_size = sum(len(fn.flatten()) for fn in source_funcs)
        target_size = sum(len(fn.flatten()) for fn in target_funcs)
        max_size = max(source_size, target_size, 1)

        # Zhang-Shasha tree edit distance
        edit_dist = simple_distance(s_root, t_root)
        tree_sim = max(0.0, 1.0 - edit_dist / max_size)

        logger.info(
            "Tree edit distance: %d (similarity=%.4f, |S|=%d, |T|=%d)",
            edit_dist, tree_sim, source_size, target_size,
        )

        return edit_dist, round(tree_sim, 4)

    def match(
        self,
        source: ControlFlowGraph,
        target: ControlFlowGraph,
    ) -> AlignmentReport:
        """
        Compare two ControlFlowGraphs and produce an AlignmentReport.

        Parameters
        ----------
        source:
            The CFG extracted from the original C code.
        target:
            The CFG extracted from the LLM-generated Java code.

        Returns
        -------
        AlignmentReport
            Contains ``is_aligned``, a list of ``Hallucination`` objects,
            summary statistics, and a confidence score.
        """
        hallucinations: list[Hallucination] = []

        source_summary = source.summary()
        target_summary = target.summary()

        # ── Level 1: Global count comparison ────────────────────────────────
        hallucinations.extend(self._compare_global_counts(source_summary, target_summary))

        # ── Level 2 & 3: Function-level alignment + per-function diff ──────
        hallucinations.extend(self._compare_functions(source.functions, target.functions))

        # ── Tree Edit Distance (Zhang-Shasha, 1989) ────────────────────────
        # This is computed IN ADDITION to the count-based hallucinations.
        # The hallucinations above give taxonomy labels; the TED gives a
        # principled, citable similarity metric.
        ted, tree_sim = self._compute_tree_edit_distance(
            source.functions, target.functions,
        )

        # ── Calculate confidence (ORIGINAL — count-based penalty) ──────────
        total_elements = max(source.total_elements, 1)
        weighted_penalty = sum(self.weights.get(h.category.value, 1.0) for h in hallucinations)
        confidence = max(0.0, 1.0 - weighted_penalty / total_elements)

        is_aligned = confidence >= self.confidence_threshold and len(hallucinations) == 0

        report = AlignmentReport(
            is_aligned=is_aligned,
            hallucinations=hallucinations,
            source_summary=source_summary,
            target_summary=target_summary,
            confidence=round(confidence, 4),
            phase="structural",
            # NEW — principled similarity metrics
            tree_edit_distance=ted,
            tree_similarity=tree_sim,
        )

        logger.info(
            "Alignment result: aligned=%s, confidence=%.2f, hallucinations=%d",
            is_aligned,
            confidence,
            len(hallucinations),
        )

        return report

    # ─────────────────────────────────────────────────────────────────────────
    # Level 1: Global count comparison
    # ─────────────────────────────────────────────────────────────────────────

    def _compare_global_counts(
        self,
        source_summary: dict[str, int],
        target_summary: dict[str, int],
    ) -> list[Hallucination]:
        """
        Compare aggregate structural counts.

        This catches gross hallucinations like "source has 3 loops,
        target has 1 loop".  Detailed per-function analysis follows.
        """
        # We don't generate hallucinations at the global level — they would
        # duplicate the per-function ones.  But we log discrepancies.
        all_types = set(source_summary.keys()) | set(target_summary.keys())
        for node_type in sorted(all_types):
            s_count = source_summary.get(node_type, 0)
            t_count = target_summary.get(node_type, 0)
            if s_count != t_count:
                logger.debug(
                    "Global count mismatch: %s — source=%d, target=%d",
                    node_type,
                    s_count,
                    t_count,
                )

        return []  # Detailed hallucinations come from per-function analysis.

    # ─────────────────────────────────────────────────────────────────────────
    # Level 2: Function-level alignment
    # ─────────────────────────────────────────────────────────────────────────

    def _compare_functions(
        self,
        source_funcs: list[ControlFlowNode],
        target_funcs: list[ControlFlowNode],
    ) -> list[Hallucination]:
        """
        Align source functions to target methods and compare each pair.

        Strategy:
            1. Match by position (source[0] → target[0], etc.)
            2. Handle surplus/deficit as missing/invented functions
        """
        hallucinations: list[Hallucination] = []

        # Align by position.
        paired = min(len(source_funcs), len(target_funcs))

        for i in range(paired):
            s_func = source_funcs[i]
            t_func = target_funcs[i]

            # Level 3: Per-function structural diff.
            hallucinations.extend(self._compare_single_function(s_func, t_func))

        # Missing functions (source has more than target).
        for i in range(paired, len(source_funcs)):
            s_func = source_funcs[i]
            hallucinations.append(
                Hallucination(
                    category=HallucinationCategory.MISSING,
                    severity=HallucinationSeverity.CRITICAL,
                    node_type="function",
                    source_location=f"{s_func.name}:{s_func.line}",
                    description=(
                        f"Function '{s_func.name}' at line {s_func.line} in source "
                        f"has no corresponding method in the target."
                    ),
                    phase_detected="structural",
                )
            )

        # Invented functions (target has more than source).
        for i in range(paired, len(target_funcs)):
            t_func = target_funcs[i]
            hallucinations.append(
                Hallucination(
                    category=HallucinationCategory.INVENTED,
                    severity=HallucinationSeverity.WARNING,
                    node_type="function",
                    target_location=f"{t_func.name}:{t_func.line}",
                    description=(
                        f"Method '{t_func.name}' at line {t_func.line} in target "
                        f"has no corresponding function in the source."
                    ),
                    phase_detected="structural",
                )
            )

        return hallucinations

    # ─────────────────────────────────────────────────────────────────────────
    # Level 3: Per-function structural diff
    # ─────────────────────────────────────────────────────────────────────────

    def _compare_single_function(
        self,
        source: ControlFlowNode,
        target: ControlFlowNode,
    ) -> list[Hallucination]:
        """
        Compare the internal structure of a single aligned function pair.

        Checks:
            - Loop counts & types (for, while, do-while)
            - Branch counts (if, switch)
            - Function call counts
            - Return statement counts
            - Nesting depth
        """
        hallucinations: list[Hallucination] = []
        func_name = source.name or "<unknown>"

        s_counts = source.count_by_type()
        t_counts = target.count_by_type()

        # Compare counts for each structural element type.
        # Exclude the "function" type itself — we're already inside one.
        check_types = [
            "for_loop",
            "while_loop",
            "do_while_loop",
            "if_branch",
            "switch",
            "case",
            "return",
            "function_call",
            "try_catch",
        ]

        for node_type in check_types:
            s_count = s_counts.get(node_type, 0)
            t_count = t_counts.get(node_type, 0)

            if s_count > t_count:
                # Missing in target
                diff = s_count - t_count
                for _ in range(diff):
                    hallucinations.append(
                        Hallucination(
                            category=HallucinationCategory.MISSING,
                            severity=HallucinationSeverity.CRITICAL,
                            node_type=node_type,
                            source_location=func_name,
                            description=(
                                f"Source function '{func_name}' has {s_count} "
                                f"{node_type}(s) but target has only {t_count}. "
                                f"{diff} {node_type}(s) missing."
                            ),
                            phase_detected="structural",
                        )
                    )
            elif t_count > s_count:
                # Invented in target
                diff = t_count - s_count
                for _ in range(diff):
                    hallucinations.append(
                        Hallucination(
                            category=HallucinationCategory.INVENTED,
                            severity=HallucinationSeverity.WARNING,
                            node_type=node_type,
                            target_location=target.name or func_name,
                            description=(
                                f"Target method '{target.name or func_name}' has "
                                f"{t_count} {node_type}(s) but source has only "
                                f"{s_count}. {diff} {node_type}(s) were invented."
                            ),
                            phase_detected="structural",
                        )
                    )

        # Check nesting depth.
        s_depth = source.depth
        t_depth = target.depth
        if abs(s_depth - t_depth) >= 1:
            hallucinations.append(
                Hallucination(
                    category=HallucinationCategory.DEPTH_MISMATCH,
                    severity=HallucinationSeverity.WARNING,
                    node_type="function",
                    source_location=func_name,
                    target_location=target.name or func_name,
                    description=(
                        f"Nesting depth mismatch in '{func_name}': "
                        f"source depth={s_depth}, target depth={t_depth}."
                    ),
                    phase_detected="structural",
                )
            )

        return hallucinations


# ─────────────────────────────────────────────────────────────────────────────
# TreeSitterVerifier — wraps the extractor + matcher as a BaseVerifier
# ─────────────────────────────────────────────────────────────────────────────


class TreeSitterVerifier(BaseVerifier):
    """
    Phase 1 verifier: tree-sitter structural extraction + counting matcher.

    This is the lightweight, fast verifier that catches superficial
    structural hallucinations (dropped loops, invented branches, etc.).
    """

    def __init__(
        self,
        confidence_threshold: float = 0.95,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._matcher = StructuralMatcher(
            confidence_threshold=confidence_threshold,
            weights=weights,
        )

    @property
    def name(self) -> str:
        return "TreeSitterVerifier"

    def verify(
        self,
        source_code: str,
        target_code: str,
        source_lang: Literal["c", "java"] = "c",
        target_lang: Literal["c", "java"] = "java",
    ) -> AlignmentReport:
        """
        Extract CFGs from both codebases and compare them.

        This method is the single entry point — it handles extraction
        and matching in one call.
        """
        source_extractor = StructuralExtractor(source_lang)
        target_extractor = StructuralExtractor(target_lang)

        source_cfg = source_extractor.extract(source_code)
        target_cfg = target_extractor.extract(target_code)

        return self._matcher.match(source_cfg, target_cfg)
