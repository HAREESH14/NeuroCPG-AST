"""
Configuration management for NeuroAST.

Uses ``pydantic-settings`` to read from ``.env`` file and environment
variables. All settings have sensible defaults — the system works
out of the box with just a Groq API key.

Environment variables are prefixed with ``NEUROAST_`` to avoid collisions.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class NeuroASTSettings(BaseSettings):
    """
    Central configuration for the NeuroAST pipeline.

    Load order (highest priority first):
        1. Explicit constructor arguments
        2. Environment variables (``NEUROAST_*``)
        3. ``.env`` file in the project root
        4. Default values below
    """

    model_config = SettingsConfigDict(
        env_prefix="NEUROAST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Don't fail on unknown env vars
    )

    # ── LLM settings ────────────────────────────────────────────────────────
    model: str = "groq/llama-3.3-70b-versatile"
    """LLM model identifier (litellm format)."""

    temperature: float = 0.2
    """Sampling temperature for translation."""

    repair_temperature: float = 0.1
    """Sampling temperature for repair (lower = more faithful)."""

    max_tokens: int = 4096
    """Maximum tokens in LLM response."""

    # ── Pipeline settings ───────────────────────────────────────────────────
    max_retries: int = 3
    """Maximum number of repair iterations before giving up."""

    verifier_type: Literal["tree-sitter", "cpg"] = "tree-sitter"
    """Which verifier to use. 'cpg' requires a running Joern server."""

    confidence_threshold: float = 0.95
    """Minimum confidence for the verifier to accept a translation."""

    # ── Hallucination weights (tunable for experiments) ──────────────────────
    weight_missing: float = 1.0
    weight_invented: float = 0.8
    weight_reordered: float = 0.3
    weight_depth_mismatch: float = 0.5

    # ── Joern CPG settings (Phase 2) ────────────────────────────────────────
    joern_host: str = "localhost"
    joern_port: int = 8080

    @property
    def hallucination_weights(self) -> dict[str, float]:
        """Return the hallucination weights as a dict for the matcher."""
        return {
            "missing": self.weight_missing,
            "invented": self.weight_invented,
            "reordered": self.weight_reordered,
            "depth_mismatch": self.weight_depth_mismatch,
        }
