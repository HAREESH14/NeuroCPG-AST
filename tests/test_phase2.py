"""Tests for Phase 2 — semantic matcher, tolerance engine, progressive verifier.

These tests do NOT require Joern to be running. They test the matching/tolerance
logic using manually constructed NormPDGs.
"""

from neuroast.verification.progressive_verifier import ProgressiveVerifier
from neuroast.verification.semantic_matcher import SemanticMatcher
from neuroast.verification.structures import (
    ControlDependency,
    DataDependency,
    Hallucination,
    HallucinationCategory,
    HallucinationSeverity,
    NormFunction,
    NormPDG,
    VariableRole,
)
from neuroast.verification.tolerance import ToleranceEngine

# ─────────────────────────────────────────────────────────────────────────────
# Test Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_data_dep(
    var: str = "x",
    role: VariableRole = VariableRole.LOCAL,
    def_ctx: str = "assignment",
    use_ctx: str = "return",
    def_line: int = 1,
    use_line: int = 5,
) -> DataDependency:
    return DataDependency(
        variable_name=var,
        variable_role=role,
        def_context=def_ctx,
        use_context=use_ctx,
        def_line=def_line,
        use_line=use_line,
    )


def _make_control_dep(
    condition: str = "i < n",
    statement: str = "sum += arr[i]",
    cond_line: int = 3,
    stmt_line: int = 4,
) -> ControlDependency:
    return ControlDependency(
        condition=condition,
        dependent_statement=statement,
        condition_line=cond_line,
        statement_line=stmt_line,
    )


def _make_func(
    name: str = "test",
    data_deps: list[DataDependency] | None = None,
    control_deps: list[ControlDependency] | None = None,
) -> NormFunction:
    return NormFunction(
        name=name,
        data_deps=data_deps or [],
        control_deps=control_deps or [],
    )


def _make_pdg(
    language: str = "c",
    functions: list[NormFunction] | None = None,
) -> NormPDG:
    return NormPDG(
        language=language,  # type: ignore[arg-type]
        functions=functions or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# SemanticMatcher Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSemanticMatcher:
    """Tests for RC2 — PDG-based semantic hallucination detection."""

    def test_identical_pdgs_aligned(self) -> None:
        """Identical NormPDGs should produce an aligned report."""
        deps = [_make_data_dep(var="sum", role=VariableRole.ACCUMULATOR)]
        source = _make_pdg("c", [_make_func("f", data_deps=deps)])
        target = _make_pdg("java", [_make_func("f", data_deps=deps)])

        matcher = SemanticMatcher()
        report = matcher.match(source, target)
        assert report.is_aligned
        assert report.data_flow_preserved

    def test_broken_def_use_detected(self) -> None:
        """Missing def→use chain should be flagged as broken_def_use."""
        source_deps = [
            _make_data_dep(
                var="sum", role=VariableRole.ACCUMULATOR, def_ctx="accumulation", use_ctx="return"
            ),
        ]
        target_deps = []  # Missing the def→use chain!

        source = _make_pdg("c", [_make_func("f", data_deps=source_deps)])
        target = _make_pdg("java", [_make_func("f", data_deps=target_deps)])

        matcher = SemanticMatcher()
        report = matcher.match(source, target)
        assert not report.is_aligned
        assert not report.data_flow_preserved

        broken = [
            h for h in report.hallucinations if h.category == HallucinationCategory.BROKEN_DEF_USE
        ]
        assert len(broken) >= 1

    def test_data_flow_invention_detected(self) -> None:
        """Extra def→use in target should be flagged as invention."""
        source_deps = []
        target_deps = [
            _make_data_dep(
                var="total",
                role=VariableRole.LOCAL,
                def_ctx="assignment",
                use_ctx="function_call_arg",
            ),
        ]

        source = _make_pdg("c", [_make_func("f", data_deps=source_deps)])
        target = _make_pdg("java", [_make_func("f", data_deps=target_deps)])

        matcher = SemanticMatcher()
        report = matcher.match(source, target)

        invented = [
            h
            for h in report.hallucinations
            if h.category == HallucinationCategory.DATA_FLOW_INVENTION
        ]
        assert len(invented) >= 1

    def test_lost_control_dep_detected(self) -> None:
        """Fewer control deps in target means a condition guard was lost."""
        source_cds = [_make_control_dep(), _make_control_dep(condition="x > 0")]
        target_cds = []  # All guards lost!

        source = _make_pdg("c", [_make_func("f", control_deps=source_cds)])
        target = _make_pdg("java", [_make_func("f", control_deps=target_cds)])

        matcher = SemanticMatcher()
        report = matcher.match(source, target)
        assert not report.control_deps_preserved

        lost = [
            h for h in report.hallucinations if h.category == HallucinationCategory.LOST_CONTROL_DEP
        ]
        assert len(lost) >= 1

    def test_function_alignment_by_name(self) -> None:
        """Functions should align by name match."""
        source = _make_pdg(
            "c",
            [
                _make_func("alpha"),
                _make_func("beta"),
            ],
        )
        target = _make_pdg(
            "java",
            [
                _make_func("beta"),  # Different order
                _make_func("alpha"),
            ],
        )

        matcher = SemanticMatcher()
        report = matcher.match(source, target)
        # Both functions match — no missing/invented
        missing = [h for h in report.hallucinations if h.category == HallucinationCategory.MISSING]
        assert len(missing) == 0

    def test_missing_function_detected(self) -> None:
        """Function in source but not target is detected."""
        source = _make_pdg("c", [_make_func("foo"), _make_func("bar")])
        target = _make_pdg("java", [_make_func("foo")])

        matcher = SemanticMatcher()
        report = matcher.match(source, target)

        missing = [
            h
            for h in report.hallucinations
            if h.category == HallucinationCategory.MISSING and h.node_type == "function"
        ]
        assert len(missing) == 1

    def test_empty_pdgs_aligned(self) -> None:
        """Two empty NormPDGs should be aligned."""
        source = _make_pdg("c")
        target = _make_pdg("java")

        matcher = SemanticMatcher()
        report = matcher.match(source, target)
        assert report.is_aligned


# ─────────────────────────────────────────────────────────────────────────────
# ToleranceEngine Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestToleranceEngine:
    """Tests for RC3 — idiom vs hallucination classification."""

    def test_loop_to_api_tolerated(self) -> None:
        """Missing for-loop should be tolerated if target uses Arrays.fill."""
        h = Hallucination(
            category=HallucinationCategory.MISSING,
            node_type="for_loop",
            description="Missing for loop",
        )
        engine = ToleranceEngine()
        remaining, tolerated = engine.apply_tolerance(
            [h],
            source_code="for (int i=0; i<n; i++) arr[i] = 0;",
            target_code="Arrays.fill(arr, 0);",
        )
        assert len(remaining) == 0
        assert len(tolerated) == 1
        assert tolerated[0].tolerance_rule == "loop_to_api"

    def test_memory_model_tolerated(self) -> None:
        """Missing malloc/free calls should be tolerated."""
        h = Hallucination(
            category=HallucinationCategory.MISSING,
            node_type="function_call",
            description="Missing function_call free",
        )
        engine = ToleranceEngine()
        remaining, tolerated = engine.apply_tolerance(
            [h],
            source_code="int* p = malloc(n * sizeof(int)); free(p);",
            target_code="int[] p = new int[n];",
        )
        assert len(remaining) == 0
        assert len(tolerated) == 1
        assert tolerated[0].tolerance_rule == "memory_model"

    def test_error_handling_invented_try_catch(self) -> None:
        """Invented try-catch for error-return patterns should be tolerated."""
        h = Hallucination(
            category=HallucinationCategory.INVENTED,
            node_type="try_catch",
            description="Invented try-catch block",
        )
        engine = ToleranceEngine()
        remaining, tolerated = engine.apply_tolerance(
            [h],
            source_code=('FILE* fp = fopen("test.txt", "r"); if (fp == NULL) return -1;'),
            target_code=(
                "try { BufferedReader br = new BufferedReader(...); } catch (Exception e) {}"
            ),
        )
        assert len(remaining) == 0
        assert len(tolerated) == 1
        assert tolerated[0].tolerance_rule == "error_handling"

    def test_genuine_hallucination_not_tolerated(self) -> None:
        """A real missing loop (no API replacement) should NOT be tolerated."""
        h = Hallucination(
            category=HallucinationCategory.MISSING,
            node_type="for_loop",
            description="Missing for loop",
        )
        engine = ToleranceEngine()
        remaining, tolerated = engine.apply_tolerance(
            [h],
            source_code="for (int i=0; i<n; i++) sum += arr[i];",
            target_code="int sum = arr[0];",  # No API replacement
        )
        assert len(remaining) == 1
        assert len(tolerated) == 0

    def test_semantic_hallucination_not_tolerated(self) -> None:
        """Semantic hallucinations (Phase 2) should never be tolerated."""
        h = Hallucination(
            category=HallucinationCategory.BROKEN_DEF_USE,
            severity=HallucinationSeverity.CRITICAL,
            node_type="data_dependency",
            description="Broken def-use",
            phase_detected="semantic",
        )
        engine = ToleranceEngine()
        remaining, tolerated = engine.apply_tolerance([h])
        assert len(remaining) == 1
        assert len(tolerated) == 0

    def test_disabled_rules(self) -> None:
        """Tolerance should not apply disabled rules."""
        h = Hallucination(
            category=HallucinationCategory.MISSING,
            node_type="for_loop",
            description="Missing for loop",
        )
        engine = ToleranceEngine(enabled_rules=["memory_model"])  # No loop_to_api!
        remaining, tolerated = engine.apply_tolerance(
            [h],
            source_code="for (int i=0; i<n; i++) arr[i] = 0;",
            target_code="Arrays.fill(arr, 0);",
        )
        assert len(remaining) == 1  # Not tolerated because rule is disabled
        assert len(tolerated) == 0

    def test_string_idiom_tolerated(self) -> None:
        """C string function → Java String method should be tolerated."""
        h = Hallucination(
            category=HallucinationCategory.MISSING,
            node_type="function_call",
            description="Missing strcmp call",
        )
        engine = ToleranceEngine()
        remaining, tolerated = engine.apply_tolerance(
            [h],
            source_code="if (strcmp(a, b) == 0)",
            target_code="if (a.equals(b))",
        )
        assert len(remaining) == 0
        assert len(tolerated) == 1
        assert tolerated[0].tolerance_rule == "string_idiom"


# ─────────────────────────────────────────────────────────────────────────────
# ProgressiveVerifier Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProgressiveVerifier:
    """Tests for RC4 — progressive verification paradigm."""

    def test_structural_only_mode(self) -> None:
        """structural_only mode should run Phase 1 only."""
        verifier = ProgressiveVerifier(mode="structural_only")
        assert verifier.name == "ProgressiveVerifier(structural_only)"

        c_code = """
        void bubbleSort(int arr[], int n) {
            for (int i = 0; i < n - 1; i++) {
                for (int j = 0; j < n - i - 1; j++) {
                    if (arr[j] > arr[j + 1]) {
                        int temp = arr[j];
                        arr[j] = arr[j + 1];
                        arr[j + 1] = temp;
                    }
                }
            }
        }
        """
        java_code = """
        public class BubbleSort {
            public static void bubbleSort(int[] arr) {
                int n = arr.length;
                for (int i = 0; i < n - 1; i++) {
                    for (int j = 0; j < n - i - 1; j++) {
                        if (arr[j] > arr[j + 1]) {
                            int temp = arr[j];
                            arr[j] = arr[j + 1];
                            arr[j + 1] = temp;
                        }
                    }
                }
            }
        }
        """
        report = verifier.verify(c_code, java_code)
        assert report.phase in ("structural", "progressive")
        # Should detect the structural match (or close to it)
        assert report.confidence > 0.5

    def test_progressive_fast_fail(self) -> None:
        """Progressive mode should fast-fail on structural issues."""
        verifier = ProgressiveVerifier(mode="progressive")

        c_code = """
        void sort(int arr[], int n) {
            for (int i = 0; i < n; i++) {
                for (int j = i + 1; j < n; j++) {
                    if (arr[i] > arr[j]) {
                        int tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                    }
                }
            }
        }
        """
        java_code = """
        public class Sort {
            public static void sort(int[] arr) {
                // Completely missing the nested loops!
                System.out.println("sorted");
            }
        }
        """
        report = verifier.verify(c_code, java_code)
        assert not report.is_aligned
        # Should have structural hallucinations
        assert len(report.hallucinations) > 0

    def test_verify_with_pdg_direct(self) -> None:
        """verify_with_pdg should work with pre-built NormPDGs."""
        verifier = ProgressiveVerifier()

        source_pdg = _make_pdg(
            "c",
            [
                _make_func(
                    "f",
                    data_deps=[
                        _make_data_dep(var="sum", role=VariableRole.ACCUMULATOR),
                    ],
                ),
            ],
        )
        target_pdg = _make_pdg(
            "java",
            [
                _make_func(
                    "f",
                    data_deps=[
                        _make_data_dep(var="sum", role=VariableRole.ACCUMULATOR),
                    ],
                ),
            ],
        )

        report = verifier.verify_with_pdg(source_pdg, target_pdg)
        assert report.is_aligned
        assert report.data_flow_preserved

    def test_verify_with_pdg_broken(self) -> None:
        """verify_with_pdg should detect semantic hallucinations."""
        verifier = ProgressiveVerifier()

        source_pdg = _make_pdg(
            "c",
            [
                _make_func(
                    "f",
                    data_deps=[
                        _make_data_dep(
                            var="sum",
                            role=VariableRole.ACCUMULATOR,
                            def_ctx="accumulation",
                            use_ctx="return",
                        ),
                    ],
                ),
            ],
        )
        target_pdg = _make_pdg(
            "java",
            [
                _make_func("f", data_deps=[]),  # Broken — missing the chain
            ],
        )

        report = verifier.verify_with_pdg(source_pdg, target_pdg)
        assert not report.data_flow_preserved
        broken = [
            h for h in report.hallucinations if h.category == HallucinationCategory.BROKEN_DEF_USE
        ]
        assert len(broken) >= 1

    def test_invalid_mode_raises(self) -> None:
        """Invalid mode should raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Invalid mode"):
            ProgressiveVerifier(mode="invalid")  # type: ignore[arg-type]
