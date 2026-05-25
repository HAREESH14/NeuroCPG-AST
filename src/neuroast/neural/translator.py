"""
LLM-based C → Java translator (Phase 1 of the pipeline).

Uses ``litellm`` for model abstraction — supports OpenAI, Anthropic,
Groq, Ollama, and any other provider through a single interface.
"""

from __future__ import annotations

import logging
import re

import litellm  # type: ignore[import-untyped]

from neuroast.neural.prompts import format_translation_prompt

logger = logging.getLogger(__name__)


class Translator:
    """
    Calls the LLM to translate C code to Java.

    Parameters
    ----------
    model:
        A ``litellm``-compatible model string (e.g. ``"groq/llama-3.3-70b-versatile"``).
    temperature:
        Sampling temperature. Lower values produce more deterministic output.
    max_tokens:
        Maximum tokens in the response.
    """

    def __init__(
        self,
        model: str = "groq/llama-3.3-70b-versatile",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def translate(self, c_source: str) -> str:
        """
        Translate C source code to Java via the LLM.

        Parameters
        ----------
        c_source:
            The raw C source code to translate.

        Returns
        -------
        str
            The raw Java code string from the LLM (with markdown fences stripped).

        Raises
        ------
        litellm.exceptions.APIError
            If the LLM call fails.
        """
        messages = format_translation_prompt(c_source)

        logger.info("Translating C → Java via %s", self.model)
        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        raw_output = response.choices[0].message.content or ""
        java_code = self._extract_code(raw_output)

        logger.debug("Translation output: %d characters", len(java_code))
        return java_code

    @staticmethod
    def _extract_code(raw: str) -> str:
        """
        Strip markdown code fences from the LLM output if present.

        Handles patterns like:
        - ```java\\n...\\n```
        - ```\\n...\\n```
        - Raw code (no fences)
        """
        # Try to extract from ```java ... ``` or ``` ... ```
        pattern = r"```(?:java)?\s*\n(.*?)```"
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            return match.group(1).strip()
        return raw.strip()
