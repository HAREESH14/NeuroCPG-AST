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
from typing import Any, Literal

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

        # Shared CPG infrastructure (lazy — created on first Phase 2 use)
        self._cpg_extractor: Any | None = None
        self._c_normalizer: Any | None = None
        self._j_normalizer: Any | None = None
        self._extraction_count: int = 0  # Track for periodic Joern cleanup

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

        Uses shared CPGExtractor + Normalizer instances to avoid
        creating hundreds of Joern websocket connections.
        """
        try:
            extractor, c_norm, j_norm = self._get_cpg_infrastructure()

            c_cpg = extractor.extract(source_code, "c")
            j_cpg = extractor.extract(target_code, "java")

            source_pdg = c_norm.normalize(c_cpg)
            target_pdg = j_norm.normalize(j_cpg)

            self._extraction_count += 1

            # Periodic Joern workspace cleanup to prevent JVM heap exhaustion.
            # Every 25 files, purge all loaded workspaces.
            if self._extraction_count % 10 == 0:
                self._purge_joern_workspaces(extractor)

            return self.verify_with_pdg(
                source_pdg,
                target_pdg,
                source_code=source_code,
                target_code=target_code,
            )
        except Exception as exc:
            logger.warning("Semantic-only verification failed: %s", exc)
            # If Joern gave a bad HTTP response, try to recover by
            # resetting the client so the next file gets a fresh connection.
            self._reset_cpg_infrastructure()
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
            extractor, c_norm, j_norm = self._get_cpg_infrastructure()

            c_cpg = extractor.extract(source_code, "c")
            j_cpg = extractor.extract(target_code, "java")

            source_pdg = c_norm.normalize(c_cpg)
            target_pdg = j_norm.normalize(j_cpg)

            self._extraction_count += 1

            if self._extraction_count % 25 == 0:
                self._purge_joern_workspaces(extractor)

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
            self._reset_cpg_infrastructure()
            # If Phase 2 fails, Phase 1 result is still valid
            phase1_report.phase = "progressive"
            return phase1_report

    # ─────────────────────────────────────────────────────────────────────────
    # CPG Infrastructure Management
    # ─────────────────────────────────────────────────────────────────────────

    def _get_cpg_infrastructure(self) -> tuple[Any, Any, Any]:
        """Lazily create and return shared CPG extractor + normalizers.

        Reuses a single CPGExtractor (and thus a single JoernClient
        websocket connection) across all files, preventing connection
        churn that crashes the Joern JVM.
        """
        if self._cpg_extractor is None:
            from neuroast.symbolic.cpg_extractor import CPGExtractor
            from neuroast.symbolic.normalizer import CPGNormalizer

            self._cpg_extractor = CPGExtractor()
            self._c_normalizer = CPGNormalizer("c")
            self._j_normalizer = CPGNormalizer("java")
            logger.info("CPG infrastructure created (shared for all files)")

        return self._cpg_extractor, self._c_normalizer, self._j_normalizer

    def _reset_cpg_infrastructure(self) -> None:
        """Reset the CPG extractor after a connection failure.

        Discards the old JoernClient so the next file gets a fresh
        websocket connection. If the Joern Docker container itself has
        crashed (e.g. from OOM), this will restart it so the benchmark
        can continue gracefully.
        """
        import subprocess
        import time as _time

        logger.info("Resetting CPG infrastructure after failure")
        self._cpg_extractor = None
        self._c_normalizer = None
        self._j_normalizer = None
        
        # Proactively check if the container is healthy; if not, restart it.
        try:
            status = subprocess.run(
                ["docker", "inspect", "--format={{.State.Health.Status}}", "neuroast_joern"],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
            
            if status != "healthy":
                logger.warning("Joern container is %s — restarting...", status)
                subprocess.run(["docker", "restart", "neuroast_joern"], check=True, timeout=30)
                # Wait for healthy
                for _ in range(12):
                    _time.sleep(10)
                    check = subprocess.run(
                        ["docker", "inspect", "--format={{.State.Health.Status}}", "neuroast_joern"],
                        capture_output=True, text=True, timeout=5
                    ).stdout.strip()
                    if check == "healthy":
                        logger.info("Joern restarted and healthy.")
                        break
        except Exception as e:
            logger.error("Failed to check/restart Joern container: %s", e)

    @staticmethod
    def _purge_joern_workspaces(extractor: Any) -> None:
        """Purge all loaded Joern workspaces to free JVM heap memory.

        Joern keeps CPG data in-memory per workspace. After importing
        many projects, the JVM heap fills up and responses degrade.

        ``workspace.reset`` fails in Docker (FileSystemException: Device
        or resource busy) because the workspace directory is a mounted
        volume. Instead, we enumerate projects and ``delete`` each one
        individually via CPGQL.
        """
        import contextlib
        import re

        try:
            client = extractor._get_client()

            # Get the list of loaded project names
            raw = client.query('workspace.projects.map(_.name).l')
            project_names = re.findall(r'"([^"]*)"', raw)

            if not project_names:
                logger.debug("No Joern workspaces to purge")
                return

            deleted = 0
            for name in project_names:
                with contextlib.suppress(Exception):
                    client.query(f'delete("{name}")')
                    deleted += 1

            logger.info(
                "Purged %d/%d Joern workspaces to free memory",
                deleted,
                len(project_names),
            )
        except Exception as exc:
            with contextlib.suppress(Exception):
                logger.warning("Workspace purge failed: %s", exc)
