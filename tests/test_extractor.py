"""Tests for neuroast.symbolic.extractor — tree-sitter structural extraction."""

from neuroast.symbolic.extractor import StructuralExtractor

# ─────────────────────────────────────────────────────────────────────────────
# C Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCExtractor:
    """Tests for C source code extraction."""

    def test_extract_bubble_sort(self, bubble_sort_c: str) -> None:
        """Should extract 2 functions with correct structure from bubble sort."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract(bubble_sort_c)

        assert cfg.language == "c"
        assert len(cfg.functions) == 2

        # bubbleSort function
        bubble = cfg.functions[0]
        assert bubble.node_type == "function"
        assert bubble.name == "bubbleSort"

        # main function
        main = cfg.functions[1]
        assert main.node_type == "function"
        assert main.name == "main"

    def test_bubble_sort_structure(self, bubble_sort_c: str) -> None:
        """bubbleSort should have nested for-loops with an if-branch inside."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract(bubble_sort_c)

        bubble = cfg.functions[0]
        counts = bubble.count_by_type()

        # bubbleSort: function > for > for > if
        assert counts.get("for_loop", 0) == 2, f"Expected 2 for_loops, got {counts}"
        assert counts.get("if_branch", 0) == 1, f"Expected 1 if_branch, got {counts}"

    def test_main_structure(self, bubble_sort_c: str) -> None:
        """main should have a for-loop and function calls."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract(bubble_sort_c)

        main = cfg.functions[1]
        counts = main.count_by_type()

        assert counts.get("for_loop", 0) == 1
        assert counts.get("function_call", 0) >= 2  # bubbleSort, printf (at least)
        assert counts.get("return", 0) == 1

    def test_nesting_depth(self, bubble_sort_c: str) -> None:
        """bubbleSort nesting: function > for > for > if → depth 3."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract(bubble_sort_c)

        bubble = cfg.functions[0]
        assert bubble.depth >= 3, f"Expected depth >= 3, got {bubble.depth}"

    def test_summary(self, bubble_sort_c: str) -> None:
        """Global summary should have the correct totals."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract(bubble_sort_c)

        s = cfg.summary()
        assert s.get("function", 0) == 2
        assert s.get("for_loop", 0) == 3  # 2 in bubbleSort + 1 in main

    def test_simple_function(self) -> None:
        """Should handle a minimal function with just a return."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract("int foo() { return 42; }")

        assert len(cfg.functions) == 1
        func = cfg.functions[0]
        assert func.name == "foo"
        assert func.count_by_type().get("return", 0) == 1

    def test_empty_source(self) -> None:
        """Should return an empty CFG for empty input."""
        extractor = StructuralExtractor("c")
        cfg = extractor.extract("")

        assert cfg.language == "c"
        assert len(cfg.functions) == 0
        assert cfg.total_elements == 0

    def test_while_loop(self) -> None:
        """Should correctly identify while loops."""
        source = """
        void f() {
            int i = 0;
            while (i < 10) {
                i++;
            }
        }
        """
        extractor = StructuralExtractor("c")
        cfg = extractor.extract(source)

        assert len(cfg.functions) == 1
        counts = cfg.functions[0].count_by_type()
        assert counts.get("while_loop", 0) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Java Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestJavaExtractor:
    """Tests for Java source code extraction."""

    def test_extract_bubble_sort(self, bubble_sort_java: str) -> None:
        """Should extract 2 methods from the BubbleSort class."""
        extractor = StructuralExtractor("java")
        cfg = extractor.extract(bubble_sort_java)

        assert cfg.language == "java"
        assert len(cfg.functions) == 2

        bubble = cfg.functions[0]
        assert bubble.name == "bubbleSort"

        main = cfg.functions[1]
        assert main.name == "main"

    def test_bubble_sort_structure(self, bubble_sort_java: str) -> None:
        """Java bubbleSort should have the same structure as C."""
        extractor = StructuralExtractor("java")
        cfg = extractor.extract(bubble_sort_java)

        bubble = cfg.functions[0]
        counts = bubble.count_by_type()

        assert counts.get("for_loop", 0) == 2
        assert counts.get("if_branch", 0) == 1

    def test_main_structure(self, bubble_sort_java: str) -> None:
        """Java main should have a for-loop and method calls."""
        extractor = StructuralExtractor("java")
        cfg = extractor.extract(bubble_sort_java)

        main = cfg.functions[1]
        counts = main.count_by_type()

        assert counts.get("for_loop", 0) == 1
        assert counts.get("function_call", 0) >= 1  # bubbleSort, println

    def test_try_catch_detection(self) -> None:
        """Should detect try-catch blocks (Java-specific)."""
        source = """
        public class Test {
            public void risky() {
                try {
                    int x = 1 / 0;
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        }
        """
        extractor = StructuralExtractor("java")
        cfg = extractor.extract(source)

        assert len(cfg.functions) == 1
        counts = cfg.functions[0].count_by_type()
        assert counts.get("try_catch", 0) == 1

    def test_enhanced_for_loop(self) -> None:
        """Java enhanced for-each should map to 'for_loop'."""
        source = """
        public class Test {
            public void iter() {
                int[] nums = {1, 2, 3};
                for (int n : nums) {
                    System.out.println(n);
                }
            }
        }
        """
        extractor = StructuralExtractor("java")
        cfg = extractor.extract(source)

        counts = cfg.functions[0].count_by_type()
        assert counts.get("for_loop", 0) == 1

    def test_empty_java_class(self) -> None:
        """An empty class should produce zero functions."""
        source = "public class Empty {}"
        extractor = StructuralExtractor("java")
        cfg = extractor.extract(source)

        assert cfg.language == "java"
        assert len(cfg.functions) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Language Comparison Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCrossLanguage:
    """Tests that verify C and Java extractors produce comparable output."""

    def test_same_function_count(self, bubble_sort_c: str, bubble_sort_java: str) -> None:
        """Both languages should produce the same number of functions."""
        c_cfg = StructuralExtractor("c").extract(bubble_sort_c)
        j_cfg = StructuralExtractor("java").extract(bubble_sort_java)

        assert len(c_cfg.functions) == len(j_cfg.functions)

    def test_same_loop_count_in_sort_function(
        self, bubble_sort_c: str, bubble_sort_java: str
    ) -> None:
        """Both should have 2 for-loops in the sort function."""
        c_cfg = StructuralExtractor("c").extract(bubble_sort_c)
        j_cfg = StructuralExtractor("java").extract(bubble_sort_java)

        c_counts = c_cfg.functions[0].count_by_type()
        j_counts = j_cfg.functions[0].count_by_type()

        assert c_counts.get("for_loop", 0) == j_counts.get("for_loop", 0)
        assert c_counts.get("if_branch", 0) == j_counts.get("if_branch", 0)
