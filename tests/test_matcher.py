"""Tests for neuroast.verification.matcher — structural matching + hallucination detection."""

from neuroast.verification.matcher import StructuralMatcher, TreeSitterVerifier
from neuroast.verification.structures import ControlFlowGraph, ControlFlowNode

# ─────────────────────────────────────────────────────────────────────────────
# StructuralMatcher Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestStructuralMatcher:
    """Tests for the core matching algorithm."""

    def _make_cfg(self, language: str, functions: list[ControlFlowNode]) -> ControlFlowGraph:
        return ControlFlowGraph(language=language, functions=functions)  # type: ignore[arg-type]

    def test_identical_programs_aligned(self) -> None:
        """Identical structures should produce is_aligned=True with 0 hallucinations."""
        func = ControlFlowNode(
            node_type="function",
            name="main",
            line=1,
            children=[
                ControlFlowNode(node_type="for_loop", line=3),
                ControlFlowNode(node_type="return", line=5),
            ],
        )
        source = self._make_cfg("c", [func])
        target = self._make_cfg("java", [func.model_copy(deep=True)])

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        assert report.is_aligned is True
        assert len(report.hallucinations) == 0
        assert report.confidence == 1.0

    def test_missing_loop_detected(self) -> None:
        """A loop in source but not in target should be detected as 'missing'."""
        source = self._make_cfg(
            "c",
            [
                ControlFlowNode(
                    node_type="function",
                    name="sort",
                    line=1,
                    children=[
                        ControlFlowNode(node_type="for_loop", line=3),
                        ControlFlowNode(node_type="for_loop", line=6),
                    ],
                ),
            ],
        )
        target = self._make_cfg(
            "java",
            [
                ControlFlowNode(
                    node_type="function",
                    name="sort",
                    line=1,
                    children=[
                        ControlFlowNode(node_type="for_loop", line=3),
                        # Second for_loop is MISSING
                    ],
                ),
            ],
        )

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        assert report.is_aligned is False
        missing = [h for h in report.hallucinations if h.category == "missing"]
        assert len(missing) >= 1
        assert any(h.node_type == "for_loop" for h in missing)

    def test_invented_branch_detected(self) -> None:
        """A branch in target but not in source should be detected as 'invented'."""
        source = self._make_cfg(
            "c",
            [
                ControlFlowNode(
                    node_type="function",
                    name="process",
                    line=1,
                    children=[
                        ControlFlowNode(node_type="while_loop", line=3),
                    ],
                ),
            ],
        )
        target = self._make_cfg(
            "java",
            [
                ControlFlowNode(
                    node_type="function",
                    name="process",
                    line=1,
                    children=[
                        ControlFlowNode(node_type="while_loop", line=3),
                        ControlFlowNode(node_type="try_catch", line=8),  # INVENTED
                    ],
                ),
            ],
        )

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        assert report.is_aligned is False
        invented = [h for h in report.hallucinations if h.category == "invented"]
        assert len(invented) >= 1
        assert any(h.node_type == "try_catch" for h in invented)

    def test_depth_mismatch_detected(self) -> None:
        """Different nesting depth should be flagged."""
        # Source: function > for > if  (depth 2)
        source_func = ControlFlowNode(
            node_type="function",
            name="f",
            line=1,
            children=[
                ControlFlowNode(
                    node_type="for_loop",
                    line=3,
                    children=[
                        ControlFlowNode(node_type="if_branch", line=4),
                    ],
                ),
            ],
        )

        # Target: function > for, if  (depth 1 — if is NOT nested inside for)
        target_func = ControlFlowNode(
            node_type="function",
            name="f",
            line=1,
            children=[
                ControlFlowNode(node_type="for_loop", line=3),
                ControlFlowNode(node_type="if_branch", line=6),
            ],
        )

        source = self._make_cfg("c", [source_func])
        target = self._make_cfg("java", [target_func])

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        depth_issues = [h for h in report.hallucinations if h.category == "depth_mismatch"]
        assert len(depth_issues) >= 1

    def test_missing_function_detected(self) -> None:
        """Source has 2 functions, target has 1 — missing function."""
        source = self._make_cfg(
            "c",
            [
                ControlFlowNode(node_type="function", name="foo", line=1),
                ControlFlowNode(node_type="function", name="bar", line=10),
            ],
        )
        target = self._make_cfg(
            "java",
            [
                ControlFlowNode(node_type="function", name="foo", line=1),
            ],
        )

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        missing_funcs = [
            h
            for h in report.hallucinations
            if h.category == "missing" and h.node_type == "function"
        ]
        assert len(missing_funcs) == 1
        assert "bar" in missing_funcs[0].description

    def test_invented_function_detected(self) -> None:
        """Target has extra function not in source — invented."""
        source = self._make_cfg(
            "c",
            [ControlFlowNode(node_type="function", name="main", line=1)],
        )
        target = self._make_cfg(
            "java",
            [
                ControlFlowNode(node_type="function", name="main", line=1),
                ControlFlowNode(node_type="function", name="toString", line=20),
            ],
        )

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        invented_funcs = [
            h
            for h in report.hallucinations
            if h.category == "invented" and h.node_type == "function"
        ]
        assert len(invented_funcs) == 1
        assert "toString" in invented_funcs[0].description

    def test_empty_programs_aligned(self) -> None:
        """Two empty programs should be aligned."""
        source = self._make_cfg("c", [])
        target = self._make_cfg("java", [])

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        assert report.is_aligned is True
        assert report.confidence == 1.0

    def test_confidence_decreases_with_hallucinations(self) -> None:
        """More hallucinations should lower the confidence score."""
        source = self._make_cfg(
            "c",
            [
                ControlFlowNode(
                    node_type="function",
                    name="f",
                    line=1,
                    children=[
                        ControlFlowNode(node_type="for_loop", line=3),
                        ControlFlowNode(node_type="for_loop", line=5),
                        ControlFlowNode(node_type="while_loop", line=7),
                        ControlFlowNode(node_type="if_branch", line=9),
                        ControlFlowNode(node_type="return", line=11),
                    ],
                ),
            ],
        )
        target = self._make_cfg(
            "java",
            [ControlFlowNode(node_type="function", name="f", line=1)],
        )

        matcher = StructuralMatcher()
        report = matcher.match(source, target)

        assert report.confidence < 0.5
        assert report.is_aligned is False


# ─────────────────────────────────────────────────────────────────────────────
# TreeSitterVerifier Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTreeSitterVerifier:
    """Integration tests: raw source code → verification verdict."""

    def test_aligned_bubble_sort(self, bubble_sort_c: str, bubble_sort_java: str) -> None:
        """Structurally equivalent C and Java bubble sort should align."""
        verifier = TreeSitterVerifier(confidence_threshold=0.5)
        report = verifier.verify(bubble_sort_c, bubble_sort_java)

        # They should be very close (might not be perfect due to printf → println diff)
        assert report.confidence > 0.5
        assert report.source_summary.get("function", 0) == 2
        assert report.target_summary.get("function", 0) == 2

    def test_hallucination_in_java_with_missing_loop(self) -> None:
        """Java code missing a loop should be detected."""
        c_source = """
        void process() {
            for (int i = 0; i < 10; i++) {
                if (i % 2 == 0) {
                    printf("%d", i);
                }
            }
        }
        """
        java_target = """
        public class Test {
            public void process() {
                // LLM dropped the for loop!
                if (true) {
                    System.out.println("hello");
                }
            }
        }
        """
        verifier = TreeSitterVerifier()
        report = verifier.verify(c_source, java_target)

        assert report.is_aligned is False
        missing = [h for h in report.hallucinations if h.category == "missing"]
        assert any(h.node_type == "for_loop" for h in missing)

    def test_hallucination_invented_try_catch(self) -> None:
        """Java code with an invented try-catch should be detected."""
        c_source = """
        int divide(int a, int b) {
            return a / b;
        }
        """
        java_target = """
        public class Test {
            public int divide(int a, int b) {
                try {
                    return a / b;
                } catch (ArithmeticException e) {
                    return 0;
                }
            }
        }
        """
        verifier = TreeSitterVerifier()
        report = verifier.verify(c_source, java_target)

        invented = [h for h in report.hallucinations if h.category == "invented"]
        assert any(h.node_type == "try_catch" for h in invented)

    def test_verifier_name(self) -> None:
        """Should report its name correctly."""
        verifier = TreeSitterVerifier()
        assert verifier.name == "TreeSitterVerifier"
