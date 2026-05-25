"""
Core data structures for NeuroAST verification pipeline.

These Pydantic models define the language-agnostic intermediate
representation (IR) that both C and Java ASTs map into. They are
the foundation of every other module.

Research Pillars:
    N1 — Deterministic verification (AlignmentReport)
    N2 — Hallucination taxonomy (Hallucination.category)
    N4 — Unified cross-language IR (ControlFlowGraph)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Node Types — The structural vocabulary shared by C and Java
# ─────────────────────────────────────────────────────────────────────────────

NodeType = Literal[
    "function",
    "for_loop",
    "while_loop",
    "do_while_loop",
    "if_branch",
    "else_branch",
    "switch",
    "case",
    "return",
    "function_call",
    "try_catch",
]
"""All structural node types recognised by the extractor and matcher."""


# ─────────────────────────────────────────────────────────────────────────────
# Hallucination Taxonomy — The categories of structural mismatch
# ─────────────────────────────────────────────────────────────────────────────

HallucinationCategory = Literal[
    "missing",  # A structure present in source is absent from target
    "invented",  # A structure absent from source is present in target
    "reordered",  # Structures exist in both but in different order
    "depth_mismatch",  # Same structure type but different nesting depth
]
"""
Categories for the structural hallucination taxonomy (Pillar N2).

- **missing**: Source has a `for_loop` at line 10; target has nothing.
- **invented**: Target contains a `try_catch`; source has no equivalent.
- **reordered**: Both have 2 `for_loop`s, but their relative order differs.
- **depth_mismatch**: Source has `if` inside `for`; target has `if` at top level.
"""


# ─────────────────────────────────────────────────────────────────────────────
# ControlFlowNode — A single structural element
# ─────────────────────────────────────────────────────────────────────────────


class ControlFlowNode(BaseModel):
    """
    A single structural element extracted from source code.

    These nodes form a tree: a function contains loops, loops contain
    branches, etc.  The tree structure preserves **nesting depth**, which
    is critical for detecting `depth_mismatch` hallucinations.
    """

    node_type: NodeType
    """The kind of structural element (loop, branch, call, etc.)."""

    name: str | None = None
    """
    Optional name for the element:
    - For ``function``: the function/method name (e.g. ``"bubbleSort"``).
    - For ``function_call``: the callee name (e.g. ``"printf"``).
    - For others: usually ``None``.
    """

    line: int = 0
    """Source line number (1-indexed) where this element appears."""

    children: list[ControlFlowNode] = Field(default_factory=list)
    """Nested structural elements (e.g. loops inside a function)."""

    @property
    def depth(self) -> int:
        """Maximum nesting depth of this subtree (0 = leaf)."""
        if not self.children:
            return 0
        return 1 + max(child.depth for child in self.children)

    def count_by_type(self) -> dict[str, int]:
        """
        Recursively count all node types in this subtree.

        Returns a dict like ``{"for_loop": 2, "if_branch": 3, ...}``.
        """
        counts: dict[str, int] = {}
        self._count_recursive(counts)
        return counts

    def _count_recursive(self, counts: dict[str, int]) -> None:
        counts[self.node_type] = counts.get(self.node_type, 0) + 1
        for child in self.children:
            child._count_recursive(counts)

    def flatten(self) -> list[ControlFlowNode]:
        """Return all nodes in this subtree as a flat list (pre-order traversal)."""
        result: list[ControlFlowNode] = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


# ─────────────────────────────────────────────────────────────────────────────
# ControlFlowGraph — The full structural fingerprint
# ─────────────────────────────────────────────────────────────────────────────


class ControlFlowGraph(BaseModel):
    """
    The complete structural fingerprint of a source file.

    This is the unified IR (Pillar N4) — both C and Java ASTs
    produce the same ``ControlFlowGraph`` structure, enabling
    cross-language comparison.
    """

    language: Literal["c", "java"]
    """Source language of the extracted code."""

    functions: list[ControlFlowNode] = Field(default_factory=list)
    """
    Top-level functions (C) or methods (Java), each with ``node_type="function"``.
    Their ``children`` contain the control-flow structures inside the function.
    """

    global_calls: list[ControlFlowNode] = Field(default_factory=list)
    """
    Function calls that appear at global scope (rare in Java, common in
    C with ``main()``-level logic).
    """

    def summary(self) -> dict[str, int]:
        """
        Aggregate count of all structural elements across the entire file.

        Returns a dict like ``{"function": 2, "for_loop": 3, "if_branch": 1, ...}``.
        This is used for the global count comparison in the matcher.
        """
        counts: dict[str, int] = {}
        for func in self.functions:
            func._count_recursive(counts)
        for call in self.global_calls:
            call._count_recursive(counts)
        return counts

    @property
    def total_elements(self) -> int:
        """Total number of structural elements in this file."""
        return sum(self.summary().values())


# ─────────────────────────────────────────────────────────────────────────────
# Hallucination — A single detected structural mismatch
# ─────────────────────────────────────────────────────────────────────────────


class Hallucination(BaseModel):
    """
    A single detected structural mismatch between source and target.

    This is the core of the hallucination taxonomy (Pillar N2).
    Each hallucination is a precise, localized finding that can be
    used to generate a targeted repair prompt.
    """

    category: HallucinationCategory
    """Type of structural mismatch."""

    node_type: str
    """The structural element involved (e.g. ``"for_loop"``, ``"if_branch"``)."""

    source_location: str = "N/A"
    """
    Where this element was expected in the source code.
    Format: ``"function_name:line_number"`` or ``"N/A"`` if invented.
    """

    target_location: str = "N/A"
    """
    Where this element was found (or expected) in the target code.
    Format: ``"method_name:line_number"`` or ``"N/A"`` if missing.
    """

    description: str
    """
    Human-readable explanation of the hallucination.
    This is used directly in the repair prompt sent to the LLM.

    Example: ``"The while loop at line 42 in source function 'process'
    is missing from the target method 'process'."``
    """

    severity: float = 1.0
    """
    Severity weight (0.0–1.0) used in the confidence calculation.
    Defaults to 1.0; the matcher may assign lower weights to
    less critical mismatches (e.g. reordered statements).
    """


# ─────────────────────────────────────────────────────────────────────────────
# AlignmentReport — The output of the structural matcher
# ─────────────────────────────────────────────────────────────────────────────


class AlignmentReport(BaseModel):
    """
    The deterministic verdict of the structural matcher (Pillar N1).

    This report is produced without any LLM involvement — it is
    pure symbolic/deterministic analysis.
    """

    is_aligned: bool
    """
    ``True`` if the source and target structures are sufficiently aligned
    (i.e. confidence >= threshold).
    """

    hallucinations: list[Hallucination] = Field(default_factory=list)
    """All detected structural mismatches, empty if ``is_aligned=True``."""

    source_summary: dict[str, int] = Field(default_factory=dict)
    """
    Aggregate structural counts for the source code.
    Example: ``{"function": 2, "for_loop": 3, "if_branch": 1}``.
    """

    target_summary: dict[str, int] = Field(default_factory=dict)
    """Aggregate structural counts for the target (LLM-generated) code."""

    confidence: float = 1.0
    """
    Structural alignment confidence score (0.0–1.0).

    Formula::

        confidence = 1.0 - Σ(h.severity) / max(total_source_elements, 1)

    A score of 1.0 means perfect structural alignment; 0.0 means
    total structural divergence.
    """

    def format_for_repair_prompt(self) -> str:
        """
        Format the hallucinations into a string suitable for inclusion
        in a targeted LLM repair prompt.

        Returns a numbered list of issues like::

            1. [MISSING] for_loop — The for loop at line 10 in source function
               'bubbleSort' is missing from the target.
            2. [INVENTED] try_catch — A try-catch block was invented in target
               method 'main' that has no equivalent in the source.
        """
        if not self.hallucinations:
            return "No structural issues detected."

        lines: list[str] = []
        for i, h in enumerate(self.hallucinations, 1):
            tag = h.category.upper()
            lines.append(f"{i}. [{tag}] {h.node_type} — {h.description}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# PipelineResult — Full audit trail for a single translation run
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResult(BaseModel):
    """
    Complete audit trail of a single C → Java translation + verification run.

    Captures every intermediate result for reproducibility and
    experiment analysis.
    """

    success: bool
    """Whether the final output passed structural verification."""

    source_code: str
    """The original C source code."""

    java_code: str
    """The final Java translation (may still have issues if ``success=False``)."""

    attempts: int
    """Total number of translation + repair iterations performed."""

    reports: list[AlignmentReport] = Field(default_factory=list)
    """
    The ``AlignmentReport`` from each iteration.  ``reports[0]`` is from
    the initial translation; ``reports[-1]`` is from the final attempt.
    """

    model: str = ""
    """The LLM model identifier used (e.g. ``"groq/llama-3.3-70b-versatile"``)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """
    Arbitrary additional data for experiment tracking.
    Examples: ``{"source_file": "bubble_sort.c", "dataset": "codenet"}``.
    """

    @property
    def final_confidence(self) -> float:
        """Confidence score from the last verification attempt."""
        if self.reports:
            return self.reports[-1].confidence
        return 0.0

    @property
    def total_hallucinations_found(self) -> int:
        """Total hallucinations detected across all iterations."""
        return sum(len(r.hallucinations) for r in self.reports)

    @property
    def hallucination_categories(self) -> dict[str, int]:
        """
        Aggregate hallucination counts by category across all iterations.

        Returns: ``{"missing": 3, "invented": 1, ...}``
        """
        cats: dict[str, int] = {}
        for report in self.reports:
            for h in report.hallucinations:
                cats[h.category] = cats.get(h.category, 0) + 1
        return cats
