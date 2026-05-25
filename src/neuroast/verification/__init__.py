"""Verification module — core alignment checking and hallucination detection."""

from neuroast.verification.structures import (
    AlignmentReport,
    ControlFlowGraph,
    ControlFlowNode,
    ControlFlowNodeType,
    Hallucination,
    HallucinationCategory,
    HallucinationSeverity,
    PipelineResult,
    TranslationAttempt,
)

__all__ = [
    "AlignmentReport",
    "ControlFlowGraph",
    "ControlFlowNode",
    "ControlFlowNodeType",
    "Hallucination",
    "HallucinationCategory",
    "HallucinationSeverity",
    "PipelineResult",
    "TranslationAttempt",
]
