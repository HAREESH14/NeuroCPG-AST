"""
Targeted LLM repair agent (Phase 4 of the pipeline).

Takes an AlignmentReport from the structural matcher and crafts
a highly specific prompt that tells the LLM exactly what to fix.

This is the core of Pillar N3 (Neuro-Symbolic Repair Loop) —
the repair prompt uses the **symbolic diagnosis** to guide the
**neural repair**.
"""

from __future__ import annotations

import logging
import re

import litellm  # type: ignore[import-untyped]

from neuroast.neural.prompts import format_repair_prompt
from neuroast.verification.structures import AlignmentReport

logger = logging.getLogger(__name__)


class RepairAgent:
    """
    Takes a hallucination report and asks the LLM to fix specific issues.

    The key insight: instead of saying "try again", we say
    "You dropped the while loop at line 42. Fix it."

    Parameters
    ----------
    model:
        A ``litellm``-compatible model string.
    temperature:
        Lower temperature for more faithful repairs.
    max_tokens:
        Maximum tokens in the response.
    """

    def __init__(
        self,
        model: str = "groq/llama-3.3-70b-versatile",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def repair(
        self,
        source_code: str,
        previous_translation: str,
        report: AlignmentReport,
    ) -> str:
        """
        Send a targeted repair prompt to the LLM.

        Parameters
        ----------
        source_code:
            The original C source code.
        previous_translation:
            The previous (incorrect) Java translation.
        report:
            The AlignmentReport from the structural matcher, containing
            precise hallucination descriptions.

        Returns
        -------
        str
            The corrected Java code from the LLM.
        """
        hallucination_text = report.format_for_repair_prompt()
        n_hallucinations = len(report.hallucinations)

        messages = format_repair_prompt(
            source_code=source_code,
            previous_translation=previous_translation,
            hallucination_report=hallucination_text,
            n_hallucinations=n_hallucinations,
        )

        logger.info(
            "Sending repair prompt to %s — %d hallucination(s) to fix",
            self.model,
            n_hallucinations,
        )

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        raw_output = response.choices[0].message.content or ""
        java_code = self._extract_code(raw_output)

        logger.debug("Repair output: %d characters", len(java_code))
        return java_code

    @staticmethod
    def _extract_code(raw: str) -> str:
        """Strip markdown code fences from the LLM output if present."""
        pattern = r"```(?:java)?\s*\n(.*?)```"
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            return match.group(1).strip()
        return raw.strip()
