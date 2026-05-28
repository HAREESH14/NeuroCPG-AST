"""
Synthetic Hallucination Injection — Recall Evaluation for NeuroAST.

Proves that NeuroAST can *detect* hallucinations (recall), not just
be correct when it does flag them (precision).

Methodology (AST-directed mutation testing):
    1. Select verified-correct (C, Java) pairs from the validation sample.
    2. Parse the Java source with tree-sitter to find structural nodes.
    3. Apply one of four AST-directed mutators to inject a known hallucination.
    4. Run NeuroAST's ProgressiveVerifier on the (C, mutated-Java) pair.
    5. Check whether NeuroAST detected the injected hallucination.
    6. Report recall = detected / injected per category.

Mutator Categories (aligned to NeuroAST's HallucinationCategory enum):
    MISSING        — Delete a for-loop (keep its body)
    INVENTED       — Wrap a statement block in try-catch
    DEPTH_MISMATCH — Wrap a statement in if(true){...}
    LOST_DATA_DEP  — Rename a variable to break def-use chain
    REORDER_STMTS  — Swap two adjacent statements (hard: same structure)
    ALGO_REPLACE   — Replace loop body logic with equivalent alt (hard: semantic-only)

Usage:
    uv run python scripts/evaluate_recall.py
    uv run python scripts/evaluate_recall.py --limit 20   # quick test
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tree_sitter import Language, Parser, Node

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
BENCHMARKS_DIR = Path("benchmarks/datasets")
RESULTS_DIR = Path("benchmarks/results")
VALIDATION_CSV = Path("results/validation_sample.csv")
OUTPUT_FILE = Path("results/recall_evaluation.json")

# ── Tree-sitter setup ─────────────────────────────────────────────────────

def _get_java_parser() -> Parser:
    """Create a tree-sitter parser for Java."""
    import tree_sitter_java as tsjava  # type: ignore[import-untyped]
    lang = Language(tsjava.language())
    parser = Parser(lang)
    return parser


def _get_c_parser() -> Parser:
    """Create a tree-sitter parser for C."""
    import tree_sitter_c as tsc  # type: ignore[import-untyped]
    lang = Language(tsc.language())
    parser = Parser(lang)
    return parser


# ── AST Node Finders ──────────────────────────────────────────────────────

def _find_nodes_by_type(root: Node, node_type: str) -> list[Node]:
    """Recursively find all nodes of a given type in the AST."""
    results: list[Node] = []
    if root.type == node_type:
        results.append(root)
    for child in root.children:
        results.extend(_find_nodes_by_type(child, node_type))
    return results


def _find_first_node_by_type(root: Node, node_type: str) -> Node | None:
    """Find the first node of a given type (DFS)."""
    nodes = _find_nodes_by_type(root, node_type)
    return nodes[0] if nodes else None


def _find_identifiers_in_assignments(root: Node) -> list[Node]:
    """Find variable identifiers on the LEFT side of assignments.

    Looks for patterns like:
        identifier = expression;  (assignment_expression)
        type identifier = expression;  (local_variable_declaration)
    """
    results: list[Node] = []

    # Java assignment_expression: left = right
    for assign in _find_nodes_by_type(root, "assignment_expression"):
        left = assign.child_by_field_name("left")
        if left and left.type == "identifier":
            results.append(left)

    # Java local_variable_declaration → variable_declarator → name
    for decl in _find_nodes_by_type(root, "variable_declarator"):
        name_node = decl.child_by_field_name("name")
        if name_node and name_node.type == "identifier":
            results.append(name_node)

    return results


# ── Mutators ──────────────────────────────────────────────────────────────
# Each mutator takes Java source bytes and returns (mutated_bytes, success).
# They use tree-sitter to find exact byte ranges, ensuring syntactic validity.

MutatorResult = tuple[bytes, bool]


def mutate_missing_loop(source: bytes, parser: Parser) -> MutatorResult:
    """MISSING: Delete a for-loop but keep its body.

    This simulates the hallucination where an LLM drops a loop construct
    but keeps the inner logic, producing code that compiles but executes
    the loop body only once instead of iterating.

    AST operation:
        for (init; cond; update) { BODY }  →  BODY
    """
    tree = parser.parse(source)
    for_nodes = _find_nodes_by_type(tree.root_node, "for_statement")

    if not for_nodes:
        return source, False

    # Pick the first for-loop
    target = for_nodes[0]
    body = target.child_by_field_name("body")
    if body is None:
        return source, False

    # Extract the body content (strip outer braces if block)
    body_text = source[body.start_byte:body.end_byte]
    if body.type == "block" and body_text.startswith(b"{") and body_text.endswith(b"}"):
        body_text = body_text[1:-1].strip()

    # Replace the entire for-statement with just its body
    mutated = source[:target.start_byte] + body_text + source[target.end_byte:]
    return mutated, True


def mutate_invented_try_catch(source: bytes, parser: Parser) -> MutatorResult:
    """INVENTED: Wrap the first method body in try-catch.

    This simulates the hallucination where an LLM adds exception handling
    that doesn't exist in the C source (C has no try-catch).

    AST operation:
        { BODY }  →  { try { BODY } catch (Exception e) { } }
    """
    tree = parser.parse(source)
    # Find the first method_declaration
    methods = _find_nodes_by_type(tree.root_node, "method_declaration")

    if not methods:
        return source, False

    method = methods[0]
    body = method.child_by_field_name("body")
    if body is None or body.type != "block":
        return source, False

    body_text = source[body.start_byte:body.end_byte]
    if not (body_text.startswith(b"{") and body_text.endswith(b"}")):
        return source, False

    inner = body_text[1:-1]
    wrapped = b"{\n    try {" + inner + b"    } catch (Exception e) { /* injected */ }\n    }"

    mutated = source[:body.start_byte] + wrapped + source[body.end_byte:]
    return mutated, True


def mutate_depth_mismatch(source: bytes, parser: Parser) -> MutatorResult:
    """DEPTH_MISMATCH: Wrap the first statement inside a method in if(true){}.

    This simulates the hallucination where an LLM adds unnecessary
    conditional guards that increase nesting depth.

    AST operation:
        statement;  →  if (true) { statement; }
    """
    tree = parser.parse(source)
    methods = _find_nodes_by_type(tree.root_node, "method_declaration")

    if not methods:
        return source, False

    method = methods[0]
    body = method.child_by_field_name("body")
    if body is None:
        return source, False

    # Find the first meaningful statement inside the body
    target_stmt: Node | None = None
    for child in body.children:
        if child.type not in ("{", "}", "line_comment", "block_comment", ""):
            target_stmt = child
            break

    if target_stmt is None:
        return source, False

    stmt_text = source[target_stmt.start_byte:target_stmt.end_byte]
    wrapped = b"if (true) { " + stmt_text + b" }"

    mutated = source[:target_stmt.start_byte] + wrapped + source[target_stmt.end_byte:]
    return mutated, True


def mutate_lost_data_dep(source: bytes, parser: Parser) -> MutatorResult:
    """LOST_DATA_DEP: Rename a variable to break a def-use chain.

    This simulates the hallucination where an LLM introduces a variable
    name that doesn't match any prior definition, breaking the data-flow
    dependency graph.

    AST operation:
        int result = expr;  →  int result_INJECTED = expr;
        (all uses of 'result' remain unchanged, breaking the chain)
    """
    tree = parser.parse(source)
    idents = _find_identifiers_in_assignments(tree.root_node)

    if not idents:
        return source, False

    # Pick the first assignment identifier
    target = idents[0]
    original_name = source[target.start_byte:target.end_byte]

    # Only rename the DEFINITION, not the uses — this breaks the def-use chain
    new_name = original_name + b"_INJECTED"
    mutated = source[:target.start_byte] + new_name + source[target.end_byte:]

    return mutated, True


def mutate_reorder_stmts(source: bytes, parser: Parser) -> MutatorResult:
    """REORDER_STMTS: Swap two adjacent statements inside a method body.

    This simulates a subtle hallucination where the LLM reorders
    operations. If the statements are independent, the reordering
    preserves structure (same node counts, same depth) so NeuroAST's
    Phase 1 structural matcher will NOT catch it. This is a known
    limitation we honestly report.

    AST operation:
        { stmt_A; stmt_B; ... }  →  { stmt_B; stmt_A; ... }
    """
    tree = parser.parse(source)
    methods = _find_nodes_by_type(tree.root_node, "method_declaration")

    if not methods:
        return source, False

    method = methods[0]
    body = method.child_by_field_name("body")
    if body is None:
        return source, False

    # Collect meaningful statements (skip braces, comments)
    stmts = [
        child for child in body.children
        if child.type not in ("{", "}", "line_comment", "block_comment", "")
    ]

    if len(stmts) < 2:
        return source, False

    # Swap the first two statements
    a, b = stmts[0], stmts[1]
    a_text = source[a.start_byte:a.end_byte]
    b_text = source[b.start_byte:b.end_byte]

    # Replace B's position with A's text, and A's position with B's text
    # We must replace from the end of the file backwards to preserve offsets
    mutated = (
        source[:a.start_byte]
        + b_text
        + source[a.end_byte:b.start_byte]
        + a_text
        + source[b.end_byte:]
    )
    return mutated, True


def mutate_algo_replace(source: bytes, parser: Parser) -> MutatorResult:
    """ALGO_REPLACE: Replace a comparison operator inside a condition.

    This simulates an algorithmic logic error where the LLM uses
    the wrong comparison (e.g., < instead of <=). The control-flow
    structure is identical (same if-branch, same nesting), so
    NeuroAST's structural Phase 1 will NOT detect this. Phase 2
    may partially catch it if the change affects data-flow edges.

    This is a known limitation: NeuroAST verifies structural and
    dependency preservation, not algorithmic correctness.

    AST operation:
        if (x < y)  →  if (x <= y)   [or > to >=, == to !=]
    """
    tree = parser.parse(source)
    # Find binary expressions with comparison operators
    binaries = _find_nodes_by_type(tree.root_node, "binary_expression")

    for binary in binaries:
        op_node = binary.child_by_field_name("operator")
        if op_node is None:
            continue

        op_text = source[op_node.start_byte:op_node.end_byte]

        # Replace < with <=, > with >=, == with !=
        replacements = {
            b"<": b"<=",
            b">": b">=",
            b"==": b"!=",
        }

        if op_text in replacements:
            new_op = replacements[op_text]
            mutated = (
                source[:op_node.start_byte]
                + new_op
                + source[op_node.end_byte:]
            )
            return mutated, True

    return source, False


# ── Mutator Registry ──────────────────────────────────────────────────────

MUTATORS: dict[str, callable] = {
    "MISSING": mutate_missing_loop,
    "INVENTED": mutate_invented_try_catch,
    "DEPTH_MISMATCH": mutate_depth_mismatch,
    "LOST_DATA_DEP": mutate_lost_data_dep,
    "REORDER_STMTS": mutate_reorder_stmts,
    "ALGO_REPLACE": mutate_algo_replace,
}


# ── Result Models ─────────────────────────────────────────────────────────

@dataclass
class InjectionResult:
    source_file: str
    model: str
    mutation_type: str
    injection_success: bool  # Was the mutator able to inject?
    detected: bool           # Did NeuroAST detect it?
    expected_category: str   # What we injected
    detected_categories: list[str] = field(default_factory=list)
    error: str | None = None


# ── Main Logic ────────────────────────────────────────────────────────────

def load_corpus() -> list[dict]:
    """Load verified-clean (C, Java) pairs — files where NeuroAST's
    progressive verifier found ZERO hallucinations.

    Using clean files is critical: if we use files that already have
    hallucinations, our injected mutation gets masked by the pre-existing
    mismatches and recall is inflated to 100%.
    """
    pairs: list[dict] = []

    for model in ["groq_llama-3.3-70b-versatile", "ollama_llama3.1_8b", "ollama_qwen2.5-coder_7b"]:
        progressive_path = Path(f"results/progressive_{model}.json")
        if not progressive_path.exists():
            logger.warning("Skipping %s — no progressive results found", model)
            continue

        try:
            with open(progressive_path) as f:
                data = json.load(f)

            for rec in data.get("records", []):
                if rec.get("total_hallucinations", 0) == 0:
                    src_file = rec["source_file"]
                    c_path = BENCHMARKS_DIR / src_file
                    java_path = RESULTS_DIR / model / src_file.replace(".c", ".java")

                    if c_path.exists() and java_path.exists():
                        pairs.append({
                            "source_file": src_file,
                            "model": model,
                            "c_path": c_path,
                            "java_path": java_path,
                        })
        except Exception as e:
            logger.warning("Failed to load %s: %s", progressive_path, e)

    logger.info("Loaded %d verified-clean pairs (0 hallucinations in progressive mode)", len(pairs))
    return pairs


def run_recall_evaluation(limit: int | None = None) -> dict:
    """Run the full recall evaluation pipeline."""
    from neuroast.verification.progressive_verifier import ProgressiveVerifier

    corpus = load_corpus()
    if limit:
        corpus = corpus[:limit]

    java_parser = _get_java_parser()

    # Use structural_only mode — avoids needing Joern for the recall test
    # This tests Phase 1 recall (MISSING, INVENTED, DEPTH_MISMATCH).
    # For LOST_DATA_DEP (Phase 2), we would need Joern running.
    verifier = ProgressiveVerifier(mode="structural_only")

    results: list[InjectionResult] = []
    summary: dict[str, dict[str, int]] = {}

    for mut_name, mut_fn in MUTATORS.items():
        summary[mut_name] = {"injected": 0, "detected": 0, "failed_injection": 0}

        for pair in corpus:
            c_code = pair["c_path"].read_text(encoding="utf-8", errors="replace")
            java_bytes = pair["java_path"].read_bytes()

            # Apply the AST-directed mutation
            mutated_bytes, injection_ok = mut_fn(java_bytes, java_parser)

            if not injection_ok:
                summary[mut_name]["failed_injection"] += 1
                results.append(InjectionResult(
                    source_file=pair["source_file"],
                    model=pair["model"],
                    mutation_type=mut_name,
                    injection_success=False,
                    detected=False,
                    expected_category=mut_name,
                    error="Mutator could not find a suitable AST node",
                ))
                continue

            summary[mut_name]["injected"] += 1
            mutated_java = mutated_bytes.decode("utf-8", errors="replace")

            # Run NeuroAST on the mutated pair
            try:
                report = verifier.verify(
                    source_code=c_code,
                    target_code=mutated_java,
                    source_lang="c",
                    target_lang="java",
                )

                detected = len(report.hallucinations) > 0
                if detected:
                    summary[mut_name]["detected"] += 1

                categories = [h.category.value for h in report.hallucinations]

                results.append(InjectionResult(
                    source_file=pair["source_file"],
                    model=pair["model"],
                    mutation_type=mut_name,
                    injection_success=True,
                    detected=detected,
                    expected_category=mut_name,
                    detected_categories=categories,
                ))
            except Exception as e:
                logger.error(
                    "Verification failed for %s/%s (%s): %s",
                    pair["model"], pair["source_file"], mut_name, e,
                )
                results.append(InjectionResult(
                    source_file=pair["source_file"],
                    model=pair["model"],
                    mutation_type=mut_name,
                    injection_success=True,
                    detected=False,
                    expected_category=mut_name,
                    error=str(e),
                ))

    # Compute recall per category
    recall_by_category: dict[str, float] = {}
    for cat, counts in summary.items():
        if counts["injected"] > 0:
            recall_by_category[cat] = round(
                counts["detected"] / counts["injected"], 4
            )
        else:
            recall_by_category[cat] = 0.0

    total_injected = sum(c["injected"] for c in summary.values())
    total_detected = sum(c["detected"] for c in summary.values())
    overall_recall = round(total_detected / max(total_injected, 1), 4)

    output = {
        "experiment": "recall_evaluation",
        "methodology": "AST-directed synthetic hallucination injection via tree-sitter",
        "corpus_size": len(corpus),
        "mutator_categories": list(MUTATORS.keys()),
        "summary": {
            "total_injected": total_injected,
            "total_detected": total_detected,
            "overall_recall": overall_recall,
            "total_failed_injections": sum(
                c["failed_injection"] for c in summary.values()
            ),
        },
        "recall_by_category": recall_by_category,
        "category_details": summary,
        "records": [
            {
                "source_file": r.source_file,
                "model": r.model,
                "mutation_type": r.mutation_type,
                "injection_success": r.injection_success,
                "detected": r.detected,
                "expected_category": r.expected_category,
                "detected_categories": r.detected_categories,
                "error": r.error,
            }
            for r in results
        ],
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Results saved to %s", OUTPUT_FILE)

    # Print summary table
    print("\n" + "=" * 60)
    print("RECALL EVALUATION RESULTS")
    print("=" * 60)
    print(f"{'Category':<20} {'Injected':>10} {'Detected':>10} {'Recall':>10}")
    print("-" * 60)
    for cat, counts in summary.items():
        recall = recall_by_category.get(cat, 0.0)
        print(f"{cat:<20} {counts['injected']:>10} {counts['detected']:>10} {recall:>10.1%}")
    print("-" * 60)
    print(f"{'OVERALL':<20} {total_injected:>10} {total_detected:>10} {overall_recall:>10.1%}")
    print("=" * 60)

    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate NeuroAST recall via synthetic hallucination injection."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit the number of corpus files to test (for quick runs).",
    )
    args = parser.parse_args()
    run_recall_evaluation(limit=args.limit)


if __name__ == "__main__":
    main()
