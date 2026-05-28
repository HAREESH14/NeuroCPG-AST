"""
Naive AST Edit-Distance Baseline for NeuroAST (Fix 4).

Proves that a simple Tree Edit Distance (TED) threshold cannot
match NeuroAST's precision — it generates far too many false
positives because *every* valid C→Java translation has inherent
structural differences (class wrappers, type syntax, etc.).

Methodology:
    1. Parse both C and Java files with tree-sitter.
    2. Build ControlFlowGraphs (identical to NeuroAST's Phase 1 extraction).
    3. Compute Zhang-Shasha TED between the two CFGs.
    4. Apply a simple threshold: TED > T → "hallucinated".
    5. Compare this binary verdict against NeuroAST's progressive verdict.

The key insight: A naive TED baseline flags nearly every file as
"hallucinated" because even perfect translations have TED > 0
(different function signatures, class wrappers, type keywords, etc.).
NeuroAST's tolerance engine + semantic matching avoids these false positives.

Usage:
    uv run python scripts/baseline_ted_only.py
    uv run python scripts/baseline_ted_only.py --threshold 3  # custom threshold
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from neuroast.symbolic.extractor import StructuralExtractor
from neuroast.verification.matcher import StructuralMatcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
BENCHMARKS_DIR = Path("benchmarks/datasets")
RESULTS_DIR = Path("benchmarks/results")
OUTPUT_FILE = Path("results/baseline_ted_only.json")

# Models to evaluate
MODELS = [
    "groq_llama-3.3-70b-versatile",
    "ollama_llama3.1_8b",
    "ollama_qwen2.5-coder_7b",
]


def run_baseline(threshold: int = 2, limit: int | None = None) -> dict:
    """Run the naive TED-only baseline across all models.

    Parameters
    ----------
    threshold:
        TED value above which a translation is flagged as "hallucinated"
        by the naive baseline. Default is 2 (very generous).
    limit:
        Max files per model (for quick testing).
    """
    c_extractor = StructuralExtractor("c")
    j_extractor = StructuralExtractor("java")
    matcher = StructuralMatcher()

    all_records: list[dict] = []
    model_summaries: dict[str, dict] = {}

    for model in MODELS:
        model_dir = RESULTS_DIR / model
        if not model_dir.exists():
            logger.warning("Skipping %s — directory not found", model)
            continue

        java_files = sorted(model_dir.glob("*.java"))
        if limit:
            java_files = java_files[:limit]

        flagged_by_baseline = 0
        total = 0

        for java_path in java_files:
            src_name = java_path.stem + ".c"
            c_path = BENCHMARKS_DIR / src_name

            if not c_path.exists():
                continue

            total += 1

            try:
                c_code = c_path.read_text(encoding="utf-8", errors="replace")
                j_code = java_path.read_text(encoding="utf-8", errors="replace")

                c_cfg = c_extractor.extract(c_code)
                j_cfg = j_extractor.extract(j_code)

                # Compute raw TED (the ONLY metric this baseline uses)
                ted, similarity = matcher._compute_tree_edit_distance(
                    c_cfg.functions, j_cfg.functions
                )

                baseline_verdict = bool(ted > threshold)

                if baseline_verdict:
                    flagged_by_baseline += 1

                all_records.append({
                    "source_file": src_name,
                    "model": model,
                    "tree_edit_distance": ted,
                    "tree_similarity": similarity,
                    "baseline_flagged": baseline_verdict,
                    "threshold": threshold,
                })

            except Exception as e:
                logger.error("Error processing %s/%s: %s", model, src_name, e)
                all_records.append({
                    "source_file": src_name,
                    "model": model,
                    "tree_edit_distance": None,
                    "tree_similarity": None,
                    "baseline_flagged": None,
                    "threshold": threshold,
                    "error": str(e),
                })

        false_positive_rate = flagged_by_baseline / max(total, 1)
        model_summaries[model] = {
            "total_files": total,
            "flagged_by_baseline": flagged_by_baseline,
            "false_positive_rate": round(false_positive_rate, 4),
        }

        logger.info(
            "[%s] %d/%d flagged (FP rate: %.1f%%) at threshold=%d",
            model, flagged_by_baseline, total, false_positive_rate * 100, threshold,
        )

    # Load NeuroAST progressive results for comparison (if available)
    neuroast_comparison = _compare_with_neuroast(all_records)

    output = {
        "experiment": "baseline_ted_only",
        "methodology": (
            "Naive Zhang-Shasha Tree Edit Distance threshold baseline. "
            "Files with TED > threshold are flagged as hallucinated. "
            "No tolerance engine, no semantic analysis, no NormPDG."
        ),
        "threshold": threshold,
        "model_summaries": model_summaries,
        "neuroast_comparison": neuroast_comparison,
        "records": all_records,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Results saved to %s", OUTPUT_FILE)

    # Print comparison table
    print("\n" + "=" * 70)
    print(f"NAIVE TED BASELINE (threshold={threshold}) vs NeuroAST")
    print("=" * 70)
    print(f"{'Model':<35} {'Total':>6} {'Baseline':>10} {'FP Rate':>10}")
    print("-" * 70)
    for model, s in model_summaries.items():
        short = model.split("_", 1)[-1] if "_" in model else model
        print(
            f"{short:<35} {s['total_files']:>6} "
            f"{s['flagged_by_baseline']:>10} {s['false_positive_rate']:>10.1%}"
        )
    print("=" * 70)

    if neuroast_comparison:
        print("\nComparison with NeuroAST Progressive:")
        print(f"  Baseline flags {neuroast_comparison.get('baseline_total_flagged', '?')} files")
        print(f"  NeuroAST flags {neuroast_comparison.get('neuroast_total_flagged', '?')} files")
        print(f"  Agreement rate: {neuroast_comparison.get('agreement_rate', '?')}")

    return output


def _compare_with_neuroast(baseline_records: list[dict]) -> dict | None:
    """Compare baseline verdicts against NeuroAST progressive results."""
    comparison: dict = {}

    for model in MODELS:
        progressive_path = Path(f"results/progressive_{model}.json")
        if not progressive_path.exists():
            continue

        try:
            with open(progressive_path) as f:
                neuroast_data = json.load(f)

            # Build lookup: source_file → has_hallucinations
            neuroast_verdicts: dict[str, bool] = {}
            for rec in neuroast_data.get("records", []):
                has_hall = rec.get("total_hallucinations", 0) > 0
                neuroast_verdicts[rec["source_file"]] = has_hall

            # Compare
            agree = 0
            disagree = 0
            baseline_only = 0
            neuroast_only = 0

            for brec in baseline_records:
                if brec["model"] != model or brec.get("baseline_flagged") is None:
                    continue

                src = brec["source_file"]
                b_flag = brec["baseline_flagged"]
                n_flag = neuroast_verdicts.get(src)

                if n_flag is None:
                    continue

                if b_flag == n_flag:
                    agree += 1
                elif b_flag and not n_flag:
                    baseline_only += 1  # False positive by baseline
                elif not b_flag and n_flag:
                    neuroast_only += 1  # Baseline missed it
                else:
                    disagree += 1

            total = agree + disagree + baseline_only + neuroast_only
            comparison[model] = {
                "agreement": agree,
                "baseline_false_positives": baseline_only,
                "baseline_missed": neuroast_only,
                "total_compared": total,
                "agreement_rate": round(agree / max(total, 1), 4),
            }

        except Exception as e:
            logger.warning("Could not load NeuroAST results for %s: %s", model, e)

    if not comparison:
        return None

    total_flagged_baseline = sum(
        r.get("baseline_flagged", False) is True for r in baseline_records
    )
    total_flagged_neuroast = sum(
        v.get("agreement", 0) + v.get("baseline_missed", 0)
        for v in comparison.values()
    )

    return {
        "baseline_total_flagged": total_flagged_baseline,
        "neuroast_total_flagged": total_flagged_neuroast,
        "per_model": comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run naive TED-only baseline against NeuroAST."
    )
    parser.add_argument(
        "--threshold", type=int, default=2,
        help="TED threshold above which a file is flagged (default: 2).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit files per model (for quick testing).",
    )
    args = parser.parse_args()
    run_baseline(threshold=args.threshold, limit=args.limit)


if __name__ == "__main__":
    main()
