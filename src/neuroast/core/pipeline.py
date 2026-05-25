"""
Main orchestration pipeline for NeuroAST.

Ties together all phases:
    1. Translate C → Java via LLM
    2. Extract ControlFlowGraphs from both
    3. Compare structures (deterministic — no LLM)
    4. If misaligned: repair with targeted prompt → goto 2
    5. Return PipelineResult with full audit trail

This implements Pillar N3 (Neuro-Symbolic Repair Loop).
"""

from __future__ import annotations

import logging
from typing import Literal

from neuroast.core.config import NeuroASTSettings
from neuroast.neural.repair import RepairAgent
from neuroast.neural.translator import Translator
from neuroast.symbolic.extractor import StructuralExtractor
from neuroast.verification.matcher import StructuralMatcher
from neuroast.verification.structures import AlignmentReport, PipelineResult

logger = logging.getLogger(__name__)


class VerificationPipeline:
    """
    Orchestrates the full Neuro-Symbolic verification loop.

    Parameters
    ----------
    settings:
        Configuration object. If ``None``, loads from ``.env`` / environment.
    """

    def __init__(self, settings: NeuroASTSettings | None = None) -> None:
        self.settings = settings or NeuroASTSettings()

        self.translator = Translator(
            model=self.settings.model,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
        )
        self.repair_agent = RepairAgent(
            model=self.settings.model,
            temperature=self.settings.repair_temperature,
            max_tokens=self.settings.max_tokens,
        )
        self.c_extractor = StructuralExtractor("c")
        self.java_extractor = StructuralExtractor("java")
        self.matcher = StructuralMatcher(
            confidence_threshold=self.settings.confidence_threshold,
            weights=self.settings.hallucination_weights,
        )

    async def run(
        self,
        c_source: str,
        source_lang: Literal["c", "java"] = "c",
        target_lang: Literal["c", "java"] = "java",
    ) -> PipelineResult:
        """
        Execute the full translate → verify → repair loop.

        Parameters
        ----------
        c_source:
            The original C source code to translate.
        source_lang:
            Language of the source (default ``"c"``).
        target_lang:
            Language of the target (default ``"java"``).

        Returns
        -------
        PipelineResult
            Complete audit trail with all intermediate reports.
        """
        reports: list[AlignmentReport] = []
        java_code = ""

        # Extract source CFG once (it doesn't change between iterations).
        source_cfg = self.c_extractor.extract(c_source)
        logger.info(
            "Source CFG: %d functions, %d total elements",
            len(source_cfg.functions),
            source_cfg.total_elements,
        )

        for attempt in range(1, self.settings.max_retries + 1):
            logger.info("── Attempt %d/%d ──", attempt, self.settings.max_retries)

            # Phase 1: Translate (or repair)
            if attempt == 1:
                java_code = await self.translator.translate(c_source)
            else:
                # Use the last report for targeted repair.
                java_code = await self.repair_agent.repair(
                    source_code=c_source,
                    previous_translation=java_code,
                    report=reports[-1],
                )

            # Phase 2: Extract target CFG
            target_cfg = self.java_extractor.extract(java_code)
            logger.info(
                "Target CFG: %d functions, %d total elements",
                len(target_cfg.functions),
                target_cfg.total_elements,
            )

            # Phase 3: Compare (deterministic)
            report = self.matcher.match(source_cfg, target_cfg)
            reports.append(report)

            logger.info(
                "Verification: aligned=%s, confidence=%.2f, hallucinations=%d",
                report.is_aligned,
                report.confidence,
                len(report.hallucinations),
            )

            if report.is_aligned:
                return PipelineResult(
                    success=True,
                    source_code=c_source,
                    java_code=java_code,
                    attempts=attempt,
                    reports=reports,
                    model=self.settings.model,
                )

        # Exhausted all retries.
        logger.warning(
            "Failed to achieve alignment after %d attempts",
            self.settings.max_retries,
        )

        return PipelineResult(
            success=False,
            source_code=c_source,
            java_code=java_code,
            attempts=self.settings.max_retries,
            reports=reports,
            model=self.settings.model,
        )
