"""
Abstract base class for verification engines.

Provides the interface that both TreeSitterVerifier (Phase 1) and
the future JoernCPGVerifier (Phase 2) must implement.  This enables
clean ablation studies (Pillar N5) — swap the verifier in config,
and the rest of the pipeline works unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from neuroast.verification.structures import AlignmentReport


class BaseVerifier(ABC):
    """
    Abstract verifier interface for structural alignment checking.

    Subclasses:
        - ``TreeSitterVerifier`` — Phase 1 (lightweight, fast)
        - ``JoernCPGVerifier``   — Phase 2 (semantic, thorough)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this verifier (used in logs and reports)."""
        ...

    @abstractmethod
    def verify(
        self,
        source_code: str,
        target_code: str,
        source_lang: Literal["c", "java"] = "c",
        target_lang: Literal["c", "java"] = "java",
    ) -> AlignmentReport:
        """
        Verify structural alignment between source and target code.

        Parameters
        ----------
        source_code:
            The original source code (C).
        target_code:
            The LLM-generated translation (Java).
        source_lang:
            Language of the source code.
        target_lang:
            Language of the target code.

        Returns
        -------
        AlignmentReport
            Deterministic verdict with hallucination details.
        """
        ...
