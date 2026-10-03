"""
Sub-Categorize Invented Hallucination Detections.

Addresses Reviewer R2.2:
  - Breaks down the dominant "Invented" category by construct type
  - Uses tree-sitter to parse the Java translation and identify
    what KIND of construct was invented
  - Categories: try_catch, helper_variable, extra_branch, wrapper_structure,
    extra_loop, extra_return, extra_function_call, other
  - Produces a new table for the paper

Usage:
    uv run python scripts/resubmission_subcategorize_invented.py
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
RESULTS_DIR = Path("results")
BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_BASE = Path("benchmarks/results")
OUTPUT_DIR = Path("results/resubmission")

# ── Sub-categories for Invented ───────────────────────────────────────────
INVENTED_SUBCATEGORIES = [
    "try_catch",           # Invented try-catch blocks
    "helper_variable",     # Invented helper/temp variables
    "extra_branch",        # Invented if/else branches
    "extra_loop",          # Invented for/while loops
    "wrapper_structure",   # Class wrappers, method wrappers
    "extra_function_call", # Invented function/method calls
    "extra_return",        # Invented return statements
    "other",               # Anything else
]


@dataclass
class InventedInstance:
    """A single Invented hallucination with sub-category."""

    model: str
    source_file: str
    confidence: float
    total_in_file: int
    invented_count_in_file: int
    sub_category: str = "other"
    evidence: str = ""


def _get_java_parser():
    """Create a tree-sitter parser for Java."""
    from tree_sitter import Language, Parser
    import tree_sitter_java as tsjava  # type: ignore[import-untyped]

    lang = Language(tsjava.language())
    parser = Parser(lang)
    return parser


def _get_c_parser():
    """Create a tree-sitter parser for C."""
    from tree_sitter import Language, Parser
    import tree_sitter_c as tsc  # type: ignore[import-untyped]

    lang = Language(tsc.language())
    parser = Parser(lang)
    return parser


def _count_node_types(tree, node_types: set[str]) -> dict[str, int]:
    """Count occurrences of specific node types in a tree-sitter parse tree."""
    counts: dict[str, int] = {}

    def _walk(node) -> None:
        if node.type in node_types:
            counts[node.type] = counts.get(node.type, 0) + 1
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return counts


def _get_all_node_types(tree) -> dict[str, int]:
    """Get all node type counts from a tree."""
    counts: dict[str, int] = {}

    def _walk(node) -> None:
        counts[node.type] = counts.get(node.type, 0) + 1
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return counts


def classify_invented_constructs(
    c_source: str,
    java_translation: str,
    c_parser,
    java_parser,
) -> list[tuple[str, str]]:
    """
    Analyze what KIND of constructs were invented in the Java translation.

    Compares structural node counts between C source and Java target
    to identify what the LLM added that wasn't in the source.

    Returns list of (sub_category, evidence) tuples.
    """
    c_tree = c_parser.parse(c_source.encode())
    j_tree = java_parser.parse(java_translation.encode())

    # Key structural node types to compare
    c_struct_types = {
        "for_statement", "while_statement", "do_statement",
        "if_statement", "else_clause",
        "switch_statement", "case_statement",
        "return_statement", "call_expression",
    }
    j_struct_types = {
        "for_statement", "while_statement", "do_statement",
        "if_statement", "else_clause",  # Note: no else_clause in Java grammar sometimes
        "switch_expression", "switch_block_statement_group",
        "return_statement", "method_invocation",
        "try_statement", "catch_clause",
        "enhanced_for_statement",
    }

    c_counts = _count_node_types(c_tree, c_struct_types)
    j_counts = _count_node_types(j_tree, j_struct_types)

    invented: list[tuple[str, str]] = []

    # Check for invented try-catch (C rarely has try-catch equivalent)
    j_try = j_counts.get("try_statement", 0)
    j_catch = j_counts.get("catch_clause", 0)
    if j_try > 0 or j_catch > 0:
        invented.append(("try_catch", f"try={j_try}, catch={j_catch}"))

    # Check for invented branches
    c_if = c_counts.get("if_statement", 0)
    j_if = j_counts.get("if_statement", 0)
    if j_if > c_if:
        invented.append(("extra_branch", f"C has {c_if} if-stmts, Java has {j_if}"))

    # Check for invented loops
    c_loops = sum(c_counts.get(t, 0) for t in ["for_statement", "while_statement", "do_statement"])
    j_loops = sum(j_counts.get(t, 0) for t in [
        "for_statement", "while_statement", "do_statement", "enhanced_for_statement"
    ])
    if j_loops > c_loops:
        invented.append(("extra_loop", f"C has {c_loops} loops, Java has {j_loops}"))

    # Check for invented function calls
    c_calls = c_counts.get("call_expression", 0)
    j_calls = j_counts.get("method_invocation", 0)
    if j_calls > c_calls + 3:  # Allow some margin for Java boilerplate
        invented.append(("extra_function_call", f"C has {c_calls} calls, Java has {j_calls}"))

    # Check for invented returns
    c_ret = c_counts.get("return_statement", 0)
    j_ret = j_counts.get("return_statement", 0)
    if j_ret > c_ret:
        invented.append(("extra_return", f"C has {c_ret} returns, Java has {j_ret}"))

    # Check for helper variables (count local variable declarations)
    j_all = _get_all_node_types(j_tree)
    c_all = _get_all_node_types(c_tree)
    j_local_decls = j_all.get("local_variable_declaration", 0)
    c_local_decls = c_all.get("declaration", 0)
    if j_local_decls > c_local_decls + 2:
        invented.append(("helper_variable", f"C has {c_local_decls} decls, Java has {j_local_decls}"))

    # Check for wrapper structures (extra classes, methods)
    j_methods = j_all.get("method_declaration", 0)
    c_functions = c_all.get("function_definition", 0)
    if j_methods > c_functions + 1:  # +1 for main() wrapper
        invented.append(("wrapper_structure", f"C has {c_functions} funcs, Java has {j_methods} methods"))

    # If nothing specific found, classify as "other"
    if not invented:
        invented.append(("other", "No specific structural difference identified"))

    return invented


def analyze_all_invented() -> dict[str, Counter]:
    """
    Analyze all Invented detections across all models.

    Returns per-model sub-category counts.
    """
    try:
        c_parser = _get_c_parser()
        java_parser = _get_java_parser()
    except ImportError:
        logger.error("tree-sitter, tree-sitter-c, or tree-sitter-java not installed!")
        logger.error("Run: uv add tree-sitter tree-sitter-c tree-sitter-java")
        raise

    per_model_counts: dict[str, Counter] = {}

    for json_file in sorted(RESULTS_DIR.glob("progressive_*.json")):
        data = json.loads(json_file.read_text())
        model_name = json_file.stem.replace("progressive_", "")
        model_dir = TRANSLATIONS_BASE / model_name

        if not model_dir.exists():
            logger.warning("Translation dir not found: %s", model_dir)
            continue

        model_counter: Counter = Counter()
        records_with_invented = [
            r for r in data.get("records", [])
            if r.get("hallucination_categories", {}).get("invented", 0) > 0
        ]

        logger.info("Analyzing %d files with Invented for %s...", len(records_with_invented), model_name)

        for record in records_with_invented:
            source_file = record["source_file"]
            c_path = BENCHMARKS_DIR / source_file
            java_path = model_dir / f"{Path(source_file).stem}.java"

            if not c_path.exists() or not java_path.exists():
                model_counter["_file_not_found"] += 1
                continue

            try:
                c_code = c_path.read_text(errors="replace")
                java_code = java_path.read_text(errors="replace")
                subcats = classify_invented_constructs(c_code, java_code, c_parser, java_parser)

                for subcat, evidence in subcats:
                    model_counter[subcat] += 1

            except Exception as e:
                logger.warning("Error analyzing %s: %s", source_file, e)
                model_counter["_parse_error"] += 1

        per_model_counts[model_name] = model_counter
        logger.info("  %s: %s", model_name, dict(model_counter))

    return per_model_counts


def export_subcategory_results(
    per_model_counts: dict[str, Counter],
    output_path: Path,
) -> None:
    """Export sub-categorization results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Aggregate across models
    total_counter: Counter = Counter()
    for model_counter in per_model_counts.values():
        total_counter += model_counter

    report = {
        "experiment": "invented_subcategorization",
        "per_model": {model: dict(counter) for model, counter in per_model_counts.items()},
        "total": dict(total_counter),
    }

    output_path.write_text(json.dumps(report, indent=2))
    logger.info("Exported to %s", output_path)

    # ── Print table ──────────────────────────────────────────────────
    all_subcats = sorted(set(total_counter.keys()) - {"_file_not_found", "_parse_error"})
    models = sorted(per_model_counts.keys())

    print("\n% ── LaTeX Table: Invented Sub-Categories ──")
    print("\\begin{table}[!h]")
    print("\\caption{Sub-Categorization of Invented Hallucinations by Construct Type}")
    print("\\label{tab:invented_subcategories}")
    print("\\centering")

    cols = "l" + "c" * len(models) + "c"
    print(f"\\begin{{tabular}}{{|{cols}|}}")
    print("\\hline")

    header = "\\textbf{Sub-Category}"
    for m in models:
        short = m.split("_", 1)[-1] if "_" in m else m
        header += f" & \\textbf{{{short}}}"
    header += " & \\textbf{Total} \\\\"
    print(header)
    print("\\hline")

    for subcat in all_subcats:
        row = subcat.replace("_", "\\_")
        total = 0
        for m in models:
            count = per_model_counts[m].get(subcat, 0)
            total += count
            row += f" & {count}"
        row += f" & \\textbf{{{total}}} \\\\"
        print(row)
        print("\\hline")

    print("\\end{tabular}")
    print("\\end{table}")


def main() -> None:
    logger.info("Sub-categorizing Invented hallucinations across all models...")
    per_model_counts = analyze_all_invented()
    export_subcategory_results(per_model_counts, OUTPUT_DIR / "invented_subcategories.json")
    logger.info("✅ Invented sub-categorization complete!")


if __name__ == "__main__":
    main()
