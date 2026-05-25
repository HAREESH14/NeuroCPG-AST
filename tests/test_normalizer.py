"""Tests for neuroast.symbolic.normalizer — cross-language CPG normalization (RC1)."""

from neuroast.symbolic.cpg_extractor import (
    CPGControlStructure,
    CPGDataFlowEdge,
    CPGMethod,
    RawCPG,
)
from neuroast.symbolic.normalizer import CPGNormalizer, validate_type_transform
from neuroast.verification.structures import VariableRole

# ─────────────────────────────────────────────────────────────────────────────
# CPGNormalizer Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCPGNormalizer:
    """Tests for RC1 — cross-language NormPDG normalization."""

    def test_normalize_empty_cpg(self) -> None:
        """Empty CPG should produce empty NormPDG."""
        cpg = RawCPG(language="c")
        normalizer = CPGNormalizer("c")
        pdg = normalizer.normalize(cpg)
        assert pdg.language == "c"
        assert len(pdg.functions) == 0

    def test_normalize_single_function(self) -> None:
        """A CPG with one non-external method should produce one NormFunction."""
        cpg = RawCPG(
            language="c",
            methods=[
                CPGMethod(name="main", line_number=1, parameters=["argc", "argv"]),
            ],
        )
        normalizer = CPGNormalizer("c")
        pdg = normalizer.normalize(cpg)
        assert len(pdg.functions) == 1
        assert pdg.functions[0].name == "main"

    def test_external_methods_excluded(self) -> None:
        """External methods (libc, JDK) should be excluded from NormPDG."""
        cpg = RawCPG(
            language="c",
            methods=[
                CPGMethod(name="main", line_number=1, is_external=False),
                CPGMethod(name="printf", line_number=0, is_external=True),
                CPGMethod(name="malloc", line_number=0, is_external=True),
            ],
        )
        normalizer = CPGNormalizer("c")
        pdg = normalizer.normalize(cpg)
        assert len(pdg.functions) == 1
        assert pdg.functions[0].name == "main"

    def test_data_flow_normalization(self) -> None:
        """Data-flow edges should be normalized into DataDependency objects."""
        cpg = RawCPG(
            language="c",
            methods=[
                CPGMethod(name="sum", line_number=1, parameters=["arr", "n"]),
            ],
            data_flow_edges=[
                CPGDataFlowEdge(
                    variable="i",
                    def_line=3,
                    def_code="for (int i = 0; ...)",
                    use_line=4,
                    use_code="arr[i]",
                    method_name="sum",
                ),
                CPGDataFlowEdge(
                    variable="result",
                    def_line=2,
                    def_code="result += arr[i]",
                    use_line=6,
                    use_code="return result",
                    method_name="sum",
                ),
            ],
        )
        normalizer = CPGNormalizer("c")
        pdg = normalizer.normalize(cpg)
        assert len(pdg.functions) == 1
        func = pdg.functions[0]
        assert len(func.data_deps) == 2

        # Loop counter detection
        i_dep = next(d for d in func.data_deps if d.variable_name == "i")
        assert i_dep.variable_role == VariableRole.LOOP_COUNTER

        # Accumulator detection
        result_dep = next(d for d in func.data_deps if d.variable_name == "result")
        assert result_dep.variable_role == VariableRole.ACCUMULATOR

    def test_parameter_role_detection(self) -> None:
        """Variables that are parameters should get PARAMETER role."""
        cpg = RawCPG(
            language="c",
            methods=[
                CPGMethod(name="f", line_number=1, parameters=["x", "y"]),
            ],
            data_flow_edges=[
                CPGDataFlowEdge(
                    variable="x",
                    def_line=1,
                    def_code="int x",
                    use_line=2,
                    use_code="return x + 1",
                    method_name="f",
                ),
            ],
        )
        normalizer = CPGNormalizer("c")
        pdg = normalizer.normalize(cpg)
        dep = pdg.functions[0].data_deps[0]
        assert dep.variable_role == VariableRole.PARAMETER

    def test_control_dep_normalization(self) -> None:
        """Control structures should be normalized into ControlDependency."""
        cpg = RawCPG(
            language="c",
            methods=[
                CPGMethod(name="f", line_number=1),
            ],
            control_structures=[
                CPGControlStructure(
                    control_structure_type="IF",
                    condition="x > 0",
                    line_number=3,
                    code="if (x > 0)",
                ),
            ],
        )
        normalizer = CPGNormalizer("c")
        pdg = normalizer.normalize(cpg)
        assert len(pdg.functions[0].control_deps) == 1
        cd = pdg.functions[0].control_deps[0]
        assert cd.condition == "x > 0"


# ─────────────────────────────────────────────────────────────────────────────
# Type Transform Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTypeTransformValidation:
    """Tests for type transform validation rules."""

    def test_valid_int_mapping(self) -> None:
        result = validate_type_transform("int", "int")
        assert result.is_valid

    def test_valid_pointer_to_array(self) -> None:
        result = validate_type_transform("int*", "int[]")
        assert result.is_valid

    def test_invalid_pointer_to_primitive(self) -> None:
        """int* → int loses pointer indirection — should be invalid."""
        result = validate_type_transform("int*", "int")
        assert not result.is_valid
        assert "loses indirection" in result.reason.lower()

    def test_valid_char_star_to_string(self) -> None:
        result = validate_type_transform("char*", "String")
        assert result.is_valid

    def test_valid_void_star_to_object(self) -> None:
        result = validate_type_transform("void*", "Object")
        assert result.is_valid

    def test_struct_to_class(self) -> None:
        result = validate_type_transform("struct Node", "class")
        assert result.is_valid

    def test_unknown_type_assumed_valid(self) -> None:
        """Unknown types should be assumed valid (conservative)."""
        result = validate_type_transform("custom_t", "CustomClass")
        assert result.is_valid
