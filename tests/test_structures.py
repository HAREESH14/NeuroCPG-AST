"""Tests for neuroast.verification.structures — core data models."""

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

# ─────────────────────────────────────────────────────────────────────────────
# ControlFlowNode
# ─────────────────────────────────────────────────────────────────────────────


class TestControlFlowNode:
    """Tests for the ControlFlowNode model."""

    def test_leaf_node(self) -> None:
        """A leaf node (no children) should have depth 0."""
        node = ControlFlowNode(node_type=ControlFlowNodeType.RETURN, line=5)
        assert node.depth == 0
        assert node.children == []
        assert node.name is None

    def test_nested_depth(self) -> None:
        """Depth should reflect the deepest nesting level."""
        inner = ControlFlowNode(node_type=ControlFlowNodeType.RETURN, line=10)
        loop = ControlFlowNode(node_type=ControlFlowNodeType.FOR_LOOP, line=8, children=[inner])
        func = ControlFlowNode(
            node_type=ControlFlowNodeType.FUNCTION, name="main", line=1, children=[loop]
        )
        assert inner.depth == 0
        assert loop.depth == 1
        assert func.depth == 2

    def test_count_by_type(self) -> None:
        """Should recursively count all node types in the subtree."""
        func = ControlFlowNode(
            node_type=ControlFlowNodeType.FUNCTION,
            name="sort",
            line=1,
            children=[
                ControlFlowNode(
                    node_type=ControlFlowNodeType.FOR_LOOP,
                    line=3,
                    children=[
                        ControlFlowNode(node_type=ControlFlowNodeType.FOR_LOOP, line=4),
                        ControlFlowNode(node_type=ControlFlowNodeType.IF_BRANCH, line=5),
                    ],
                ),
                ControlFlowNode(node_type=ControlFlowNodeType.RETURN, line=10),
            ],
        )
        counts = func.count_by_type()
        assert counts == {
            "function": 1,
            "for_loop": 2,
            "if_branch": 1,
            "return": 1,
        }

    def test_flatten(self) -> None:
        """Flatten should return all nodes in pre-order."""
        child1 = ControlFlowNode(node_type=ControlFlowNodeType.FOR_LOOP, line=3)
        child2 = ControlFlowNode(node_type=ControlFlowNodeType.RETURN, line=5)
        func = ControlFlowNode(
            node_type=ControlFlowNodeType.FUNCTION, name="f", line=1, children=[child1, child2]
        )
        flat = func.flatten()
        assert len(flat) == 3
        assert flat[0].node_type == ControlFlowNodeType.FUNCTION
        assert flat[1].node_type == ControlFlowNodeType.FOR_LOOP
        assert flat[2].node_type == ControlFlowNodeType.RETURN

    def test_serialization_roundtrip(self) -> None:
        """Node should serialize to JSON and deserialize back identically."""
        node = ControlFlowNode(
            node_type=ControlFlowNodeType.FUNCTION,
            name="main",
            line=1,
            children=[
                ControlFlowNode(node_type=ControlFlowNodeType.FOR_LOOP, line=5),
            ],
        )
        json_str = node.model_dump_json()
        restored = ControlFlowNode.model_validate_json(json_str)
        assert restored == node
        assert restored.children[0].node_type == ControlFlowNodeType.FOR_LOOP


# ─────────────────────────────────────────────────────────────────────────────
# ControlFlowGraph
# ─────────────────────────────────────────────────────────────────────────────


class TestControlFlowGraph:
    """Tests for the ControlFlowGraph model."""

    def test_empty_graph(self) -> None:
        """An empty graph should have zero elements."""
        cfg = ControlFlowGraph(language="c")
        assert cfg.summary() == {}
        assert cfg.total_elements == 0

    def test_summary_counts(self) -> None:
        """Summary should aggregate counts across all functions."""
        cfg = ControlFlowGraph(
            language="c",
            functions=[
                ControlFlowNode(
                    node_type=ControlFlowNodeType.FUNCTION,
                    name="a",
                    line=1,
                    children=[
                        ControlFlowNode(node_type=ControlFlowNodeType.FOR_LOOP, line=3),
                    ],
                ),
                ControlFlowNode(
                    node_type=ControlFlowNodeType.FUNCTION,
                    name="b",
                    line=10,
                    children=[
                        ControlFlowNode(node_type=ControlFlowNodeType.FOR_LOOP, line=12),
                        ControlFlowNode(node_type=ControlFlowNodeType.WHILE_LOOP, line=15),
                    ],
                ),
            ],
        )
        s = cfg.summary()
        assert s["function"] == 2
        assert s["for_loop"] == 2
        assert s["while_loop"] == 1
        assert cfg.total_elements == 5

    def test_language_literal(self) -> None:
        """Language must be 'c' or 'java'."""
        cfg_c = ControlFlowGraph(language="c")
        cfg_j = ControlFlowGraph(language="java")
        assert cfg_c.language == "c"
        assert cfg_j.language == "java"


# ─────────────────────────────────────────────────────────────────────────────
# Hallucination
# ─────────────────────────────────────────────────────────────────────────────


class TestHallucination:
    """Tests for the Hallucination model."""

    def test_missing_hallucination(self) -> None:
        h = Hallucination(
            category=HallucinationCategory.MISSING,
            severity=HallucinationSeverity.CRITICAL,
            node_type="for_loop",
            source_location="bubbleSort:10",
            description="The for loop at line 10 is missing from the target.",
        )
        assert h.category == HallucinationCategory.MISSING
        assert h.severity == HallucinationSeverity.CRITICAL
        assert h.target_location == "N/A"
        assert h.phase_detected == "structural"

    def test_invented_hallucination(self) -> None:
        h = Hallucination(
            category=HallucinationCategory.INVENTED,
            severity=HallucinationSeverity.WARNING,
            node_type="try_catch",
            target_location="main:5",
            description="A try-catch block was invented in target method 'main'.",
        )
        assert h.category == HallucinationCategory.INVENTED
        assert h.source_location == "N/A"
        assert h.severity == HallucinationSeverity.WARNING

    def test_all_categories(self) -> None:
        """All structural categories should be valid."""
        for cat in (
            HallucinationCategory.MISSING,
            HallucinationCategory.INVENTED,
            HallucinationCategory.REORDERED,
            HallucinationCategory.DEPTH_MISMATCH,
        ):
            h = Hallucination(
                category=cat,
                node_type="for_loop",
                description="test",
            )
            assert h.category == cat
            assert h.category.is_structural

    def test_semantic_categories(self) -> None:
        """All semantic categories should be valid."""
        for cat in (
            HallucinationCategory.BROKEN_DEF_USE,
            HallucinationCategory.LOST_CONTROL_DEP,
            HallucinationCategory.INVALID_TYPE_TRANSFORM,
            HallucinationCategory.DATA_FLOW_INVENTION,
        ):
            h = Hallucination(
                category=cat,
                node_type="variable",
                description="test",
                phase_detected="semantic",
            )
            assert h.category.is_semantic
            assert not h.category.is_structural

    def test_idiom_categories(self) -> None:
        """All idiom categories should be tolerated."""
        for cat in (
            HallucinationCategory.VALID_API_REPLACE,
            HallucinationCategory.VALID_MEMORY_MODEL,
            HallucinationCategory.VALID_ERROR_HANDLING,
        ):
            h = Hallucination(
                category=cat,
                node_type="function_call",
                description="test",
                phase_detected="semantic",
            )
            assert h.category.is_idiom
            assert not h.category.is_structural
            assert not h.category.is_semantic


# ─────────────────────────────────────────────────────────────────────────────
# AlignmentReport
# ─────────────────────────────────────────────────────────────────────────────


class TestAlignmentReport:
    """Tests for the AlignmentReport model."""

    def test_aligned_report(self) -> None:
        """A fully aligned report should have no hallucinations."""
        report = AlignmentReport(
            is_aligned=True,
            source_summary={"function": 1, "for_loop": 2},
            target_summary={"function": 1, "for_loop": 2},
            confidence=1.0,
        )
        assert report.is_aligned is True
        assert report.hallucinations == []
        assert report.confidence == 1.0

    def test_misaligned_report(self) -> None:
        """A misaligned report should have hallucinations and lower confidence."""
        report = AlignmentReport(
            is_aligned=False,
            hallucinations=[
                Hallucination(
                    category=HallucinationCategory.MISSING,
                    node_type="for_loop",
                    description="Missing loop",
                ),
            ],
            source_summary={"function": 1, "for_loop": 2},
            target_summary={"function": 1, "for_loop": 1},
            confidence=0.5,
        )
        assert report.is_aligned is False
        assert len(report.hallucinations) == 1
        assert report.confidence == 0.5

    def test_format_for_repair_prompt(self) -> None:
        """The repair prompt formatter should produce numbered lines."""
        report = AlignmentReport(
            is_aligned=False,
            hallucinations=[
                Hallucination(
                    category=HallucinationCategory.MISSING,
                    node_type="for_loop",
                    description="Missing loop at line 10",
                ),
                Hallucination(
                    category=HallucinationCategory.INVENTED,
                    node_type="try_catch",
                    description="Invented try-catch in method main",
                ),
            ],
            confidence=0.3,
        )
        text = report.format_for_repair_prompt()
        assert "1. [MISSING]" in text
        assert "2. [INVENTED]" in text
        assert "for_loop" in text
        assert "try_catch" in text

    def test_empty_repair_prompt(self) -> None:
        """No hallucinations should produce a clean message."""
        report = AlignmentReport(is_aligned=True, confidence=1.0)
        assert "No structural issues" in report.format_for_repair_prompt()

    def test_phase_filtering(self) -> None:
        """Should filter hallucinations by phase correctly."""
        report = AlignmentReport(
            is_aligned=False,
            confidence=0.3,
            hallucinations=[
                Hallucination(
                    category=HallucinationCategory.MISSING,
                    node_type="for_loop",
                    description="struct",
                    phase_detected="structural",
                ),
                Hallucination(
                    category=HallucinationCategory.BROKEN_DEF_USE,
                    node_type="variable",
                    description="sem",
                    phase_detected="semantic",
                ),
                Hallucination(
                    category=HallucinationCategory.VALID_API_REPLACE,
                    node_type="call",
                    description="idiom",
                    phase_detected="semantic",
                ),
            ],
        )
        assert len(report.structural_hallucinations) == 1
        assert len(report.semantic_hallucinations) == 1
        assert len(report.tolerated_idioms) == 1


# ─────────────────────────────────────────────────────────────────────────────
# PipelineResult
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineResult:
    """Tests for the PipelineResult model."""

    def _make_empty_cfg(self) -> ControlFlowGraph:
        return ControlFlowGraph(language="c")

    def _make_aligned_report(self) -> AlignmentReport:
        return AlignmentReport(is_aligned=True, confidence=1.0)

    def _make_misaligned_report(self) -> AlignmentReport:
        return AlignmentReport(
            is_aligned=False,
            hallucinations=[
                Hallucination(
                    category=HallucinationCategory.MISSING,
                    node_type="for_loop",
                    description="x",
                ),
            ],
            confidence=0.5,
        )

    def test_successful_result(self) -> None:
        report = self._make_aligned_report()
        result = PipelineResult(
            success=True,
            source_code="int main() { return 0; }",
            java_code="public class Main { ... }",
            attempts=1,
            source_cfg=self._make_empty_cfg(),
            final_report=report,
            attempt_history=[
                TranslationAttempt(
                    attempt_number=1,
                    java_code="public class Main { ... }",
                    alignment_report=report,
                ),
            ],
            model="groq/llama-3.3-70b-versatile",
        )
        assert result.success is True
        assert result.final_report.confidence == 1.0

    def test_failed_result_with_hallucinations(self) -> None:
        report1 = self._make_misaligned_report()
        report2 = AlignmentReport(
            is_aligned=False,
            hallucinations=[
                Hallucination(
                    category=HallucinationCategory.MISSING,
                    node_type="for_loop",
                    description="x",
                ),
                Hallucination(
                    category=HallucinationCategory.INVENTED,
                    node_type="try_catch",
                    description="y",
                ),
            ],
            confidence=0.3,
        )
        result = PipelineResult(
            success=False,
            source_code="...",
            java_code="...",
            attempts=3,
            source_cfg=self._make_empty_cfg(),
            final_report=report2,
            attempt_history=[
                TranslationAttempt(attempt_number=1, java_code="v1", alignment_report=report1),
                TranslationAttempt(attempt_number=2, java_code="v2", alignment_report=report2),
            ],
        )
        assert result.success is False
        assert result.final_report.confidence == 0.3
        assert len(result.final_report.hallucinations) == 2

    def test_serialization(self) -> None:
        """PipelineResult should round-trip through JSON."""
        result = PipelineResult(
            success=True,
            source_code="int x;",
            java_code="int x;",
            attempts=1,
            source_cfg=self._make_empty_cfg(),
            final_report=self._make_aligned_report(),
            model="test",
        )
        json_str = result.model_dump_json()
        restored = PipelineResult.model_validate_json(json_str)
        assert restored.success is True
        assert restored.model == "test"
