"""
Progressive Verifier — Two-phase staged verification (RC4).

Implements the progressive verification paradigm:
    Phase 1 (tree-sitter): Fast structural check (~0.3s)
    Phase 2 (Joern CPG):   Deep semantic check (~2-5s, only if Phase 1 passes)

The progressive strategy is:
    - If Phase 1 FAILS: report structural hallucinations immediately (fast path)
    - If Phase 1 PASSES: run Phase 2 to catch semantic hallucinations (thorough path)

This gives the speed of structural checking for obvious errors and the depth
of semantic checking for subtle ones.

★ RESEARCH CONTRIBUTION RC4

The ablation mode parameter enables clean comparison:
    - ``structural_only``: Phase 1 only (for baseline)
    - ``semantic_only``: Phase 2 only (for ablation)
    - ``progressive``: Phase 1 → Phase 2 (the proposed approach)
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from neuroast.verification.base import BaseVerifier
from neuroast.verification.matcher import TreeSitterVerifier
from neuroast.verification.semantic_matcher import SemanticMatcher
from neuroast.verification.structures import (
    AlignmentReport,
    NormPDG,
    SemanticAlignmentReport,
)
from neuroast.verification.tolerance import ToleranceEngine

logger = logging.getLogger(__name__)


class ProgressiveVerifier(BaseVerifier):
    """Two-phase progressive verification with ablation support.

    ★ RESEARCH CONTRIBUTION RC4

    Parameters
    ----------
    structural_verifier:
        Phase 1 tree-sitter verifier.
    semantic_matcher:
        Phase 2 PDG-based semantic matcher.
    tolerance_engine:
        Idiom tolerance filter (RC3). Set to ``None`` to disable tolerance.
    mode:
        Verification mode. One of:
        - ``"structural_only"``: Phase 1 only (baseline for ablation)
        - ``"semantic_only"``: Phase 2 only (requires NormPDG input)
        - ``"progressive"``: Phase 1 → Phase 2 (the proposed approach)
    """

    VALID_MODES = ("structural_only", "semantic_only", "progressive")

    def __init__(
        self,
        structural_verifier: TreeSitterVerifier | None = None,
        semantic_matcher: SemanticMatcher | None = None,
        tolerance_engine: ToleranceEngine | None = None,
        mode: Literal["structural_only", "semantic_only", "progressive"] = "progressive",
    ) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(f"Invalid mode: {mode!r}. Must be one of {self.VALID_MODES}")

        self._structural = structural_verifier or TreeSitterVerifier()
        self._semantic = semantic_matcher or SemanticMatcher()
        self._tolerance = tolerance_engine or ToleranceEngine()
        self.mode = mode

        logger.info("ProgressiveVerifier initialized in mode=%s", mode)

    @property
    def name(self) -> str:
        return f"ProgressiveVerifier({self.mode})"

    def verify(
        self,
        source_code: str,
        target_code: str,
        source_lang: Literal["c", "java"] = "c",
        target_lang: Literal["c", "java"] = "java",
    ) -> AlignmentReport:
        """Run verification using the configured mode.

        For ``progressive`` mode:
        1. Run Phase 1 (tree-sitter structural comparison)
        2. If Phase 1 fails → return immediately with structural hallucinations
        3. If Phase 1 passes → run Phase 2 (semantic check via NormPDG)
        4. Apply tolerance rules to filter valid idiom transformations
        5. Return merged report

        Parameters
        ----------
        source_code:
            The original C source code.
        target_code:
            The translated Java code.
        source_lang:
            Language of source (default ``"c"``).
        target_lang:
            Language of target (default ``"java"``).

        Returns
        -------
        AlignmentReport
            The verification result (may be a SemanticAlignmentReport for Phase 2).
        """
        if self.mode == "structural_only":
            return self._run_structural(source_code, target_code, source_lang, target_lang)
        elif self.mode == "semantic_only":
            return self._run_semantic_standalone(source_code, target_code)
        else:
            return self._run_progressive(source_code, target_code, source_lang, target_lang)

    def verify_with_pdg(
        self,
        source_pdg: NormPDG,
        target_pdg: NormPDG,
        source_code: str = "",
        target_code: str = "",
        phase1_report: AlignmentReport | None = None,
    ) -> SemanticAlignmentReport:
        """Run Phase 2 semantic verification with pre-extracted NormPDGs.

        This is the preferred entry point when the caller already has
        NormPDGs (e.g., from the CPGExtractor + Normalizer).

        Parameters
        ----------
        source_pdg:
            NormPDG of the C source.
        target_pdg:
            NormPDG of the Java target.
        source_code:
            Raw source code (for tolerance rule pattern matching).
        target_code:
            Raw target code (for tolerance rule pattern matching).
        phase1_report:
            Optional Phase 1 report (for merging timing data).

        Returns
        -------
        SemanticAlignmentReport
            Detailed semantic verification result.
        """
        # Run semantic matcher
        semantic_report = self._semantic.match(source_pdg, target_pdg)

        # Apply tolerance rules
        if self._tolerance:
            remaining, tolerated = self._tolerance.apply_tolerance(
                semantic_report.hallucinations,
                source_pdg=source_pdg,
                target_pdg=target_pdg,
                source_code=source_code,
                target_code=target_code,
            )
            semantic_report.hallucinations = remaining
            semantic_report.tolerated_transformations = tolerated

            # Recalculate alignment after tolerance
            semantic_report.is_aligned = (
                len(remaining) == 0
                and semantic_report.confidence >= self._semantic.confidence_threshold
            )

        # Merge timing from Phase 1 if available
        if phase1_report:
            semantic_report.phase1_time_ms = phase1_report.verification_time_ms

        semantic_report.phase = "progressive"
        return semantic_report

    # ─────────────────────────────────────────────────────────────────────────
    # Internal runners
    # ─────────────────────────────────────────────────────────────────────────

    def _run_structural(
        self,
        source_code: str,
        target_code: str,
        source_lang: Literal["c", "java"] = "c",
        target_lang: Literal["c", "java"] = "java",
    ) -> AlignmentReport:
        """Run Phase 1 only."""
        start = time.perf_counter()
        report = self._structural.verify(source_code, target_code, source_lang, target_lang)
        report.verification_time_ms = (time.perf_counter() - start) * 1000
        report.phase = "structural"
        return report

    def _run_semantic_standalone(
        self,
        source_code: str,
        target_code: str,
    ) -> AlignmentReport:
        """Run Phase 2 only (requires CPG extraction — best-effort).

        Note: In standalone mode, we attempt CPG extraction. If Joern is
        not available, we return an empty report with a warning.
        """
        try:
            from neuroast.symbolic.cpg_extractor import CPGExtractor
            from neuroast.symbolic.normalizer import CPGNormalizer

            extractor = CPGExtractor()
            c_normalizer = CPGNormalizer("c")
            j_normalizer = CPGNormalizer("java")

            c_cpg = extractor.extract(source_code, "c")
            j_cpg = extractor.extract(target_code, "java")

            source_pdg = c_normalizer.normalize(c_cpg)
            target_pdg = j_normalizer.normalize(j_cpg)

            return self.verify_with_pdg(
                source_pdg,
                target_pdg,
                source_code=source_code,
                target_code=target_code,
            )
        except Exception as exc:
            logger.warning("Semantic-only verification failed: %s", exc)
            return AlignmentReport(
                is_aligned=False,
                confidence=0.0,
                phase="semantic",
            )

    def _run_progressive(
        self,
        source_code: str,
        target_code: str,
        source_lang: Literal["c", "java"] = "c",
        target_lang: Literal["c", "java"] = "java",
    ) -> AlignmentReport:
        """Run the progressive pipeline (Phase 1 → Phase 2).

        Phase 1 is always run. Phase 2 runs only if Phase 1 passes.
        This optimization saves ~2-5s for programs with gross structural
        hallucinations (which Phase 1 catches instantly).
        """
        # Phase 1: structural check (fast)
        phase1_report = self._run_structural(source_code, target_code, source_lang, target_lang)

        if not phase1_report.is_aligned:
            # Apply tolerance to Phase 1 hallucinations before giving up
            if self._tolerance:
                remaining, tolerated = self._tolerance.apply_tolerance(
                    phase1_report.hallucinations,
                    source_code=source_code,
                    target_code=target_code,
                )
                phase1_report.hallucinations = remaining

                if len(remaining) == 0:
                    # All Phase 1 issues were tolerated — proceed to Phase 2
                    logger.info(
                        "Phase 1 hallucinations all tolerated (%d idioms) — proceeding to Phase 2",
                        len(tolerated),
                    )
                else:
                    # Genuine structural issues — fast fail
                    logger.info(
                        "Phase 1 FAILED: %d structural hallucinations (skipping Phase 2)",
                        len(remaining),
                    )
                    phase1_report.phase = "progressive"
                    return phase1_report
            else:
                logger.info(
                    "Phase 1 FAILED: %d hallucinations (skipping Phase 2)",
                    len(phase1_report.hallucinations),
                )
                phase1_report.phase = "progressive"
                return phase1_report

        # Phase 2: semantic check (deep — only if Phase 1 passed or was tolerated)
        logger.info("Phase 1 PASSED — running Phase 2 semantic verification")

        try:
            from neuroast.symbolic.cpg_extractor import CPGExtractor
            from neuroast.symbolic.normalizer import CPGNormalizer

            extractor = CPGExtractor()
            c_normalizer = CPGNormalizer("c")
            j_normalizer = CPGNormalizer("java")

            c_cpg = extractor.extract(source_code, "c")
            j_cpg = extractor.extract(target_code, "java")

            source_pdg = c_normalizer.normalize(c_cpg)
            target_pdg = j_normalizer.normalize(j_cpg)

            return self.verify_with_pdg(
                source_pdg,
                target_pdg,
                source_code=source_code,
                target_code=target_code,
                phase1_report=phase1_report,
            )
        except Exception as exc:
            logger.warning(
                "Phase 2 failed (Joern unavailable?): %s — returning Phase 1 result",
                exc,
            )
            # If Phase 2 fails, Phase 1 result is still valid
            phase1_report.phase = "progressive"
            return phase1_report
