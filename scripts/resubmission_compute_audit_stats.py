"""
Compute Audit Statistics from Annotated CSVs.

Addresses Reviewer R1.2 / R2.1 / R2.2:
  - Per-category precision with 95% Clopper-Pearson confidence intervals
  - Cohen's kappa for inter-annotator agreement
  - Precision-adjusted prevalence estimates per model
  - Sub-category breakdown for Invented (try-catch, helper_var, etc.)

Usage:
    uv run python scripts/resubmission_compute_audit_stats.py
    uv run python scripts/resubmission_compute_audit_stats.py \\
        --annotator-a results/resubmission/audit_annotator_A_filled.csv \\
        --annotator-b results/resubmission/audit_annotator_B_filled.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
RESULTS_DIR = Path("results")
OUTPUT_DIR = Path("results/resubmission")


# ── Statistical Computations ──────────────────────────────────────────────


def clopper_pearson_ci(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """
    Exact Clopper-Pearson binomial confidence interval.

    Uses the relationship between the binomial and the beta distribution.
    Falls back to a simple implementation using scipy if available,
    otherwise uses a pure-Python beta quantile approximation.

    Parameters
    ----------
    successes : Number of true positives
    total : Total number of inspected instances
    confidence : Confidence level (default: 0.95)

    Returns
    -------
    (lower, upper) : Bounds of the confidence interval
    """
    alpha = 1.0 - confidence

    if total == 0:
        return (0.0, 1.0)

    try:
        from scipy.stats import beta as beta_dist

        if successes == 0:
            lower = 0.0
        else:
            lower = beta_dist.ppf(alpha / 2, successes, total - successes + 1)

        if successes == total:
            upper = 1.0
        else:
            upper = beta_dist.ppf(1 - alpha / 2, successes + 1, total - successes)

        return (float(lower), float(upper))

    except ImportError:
        # Pure-Python fallback using normal approximation with continuity correction
        logger.warning("scipy not found — using Wilson interval approximation")
        p_hat = successes / total
        z = 1.96  # For 95% CI
        denominator = 1 + z**2 / total
        centre = (p_hat + z**2 / (2 * total)) / denominator
        margin = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denominator
        return (max(0.0, centre - margin), min(1.0, centre + margin))


def cohens_kappa(
    labels_a: list[str],
    labels_b: list[str],
) -> float:
    """
    Compute Cohen's kappa for inter-annotator agreement.

    Parameters
    ----------
    labels_a : Annotator A's labels (e.g., ["Y", "N", "Y", ...])
    labels_b : Annotator B's labels (same order, same items)

    Returns
    -------
    kappa : Cohen's kappa coefficient (-1 to 1, where 1 = perfect agreement)
    """
    if len(labels_a) != len(labels_b):
        raise ValueError(
            f"Label lists must have same length: {len(labels_a)} vs {len(labels_b)}"
        )

    n = len(labels_a)
    if n == 0:
        return 0.0

    # Get all unique categories
    categories = sorted(set(labels_a) | set(labels_b))

    # Build confusion matrix
    matrix: dict[tuple[str, str], int] = {}
    for cat_a in categories:
        for cat_b in categories:
            matrix[(cat_a, cat_b)] = 0

    for a_label, b_label in zip(labels_a, labels_b):
        matrix[(a_label, b_label)] += 1

    # Observed agreement
    p_observed = sum(matrix[(c, c)] for c in categories) / n

    # Expected agreement (by chance)
    p_expected = 0.0
    for c in categories:
        row_total = sum(matrix[(c, c2)] for c2 in categories)
        col_total = sum(matrix[(c2, c)] for c2 in categories)
        p_expected += (row_total / n) * (col_total / n)

    if p_expected == 1.0:
        return 1.0  # Perfect agreement edge case

    kappa = (p_observed - p_expected) / (1 - p_expected)
    return kappa


@dataclass
class CategoryStats:
    """Statistics for a single hallucination category."""

    category: str
    total: int = 0
    true_positives: int = 0
    false_positives: int = 0
    precision: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0


@dataclass
class AuditResults:
    """Complete results from the expanded audit."""

    total_instances: int = 0
    overall_precision: float = 0.0
    overall_ci: tuple[float, float] = (0.0, 1.0)
    per_category: list[CategoryStats] = field(default_factory=list)
    cohens_kappa: float | None = None
    kappa_interpretation: str = ""
    invented_subcategories: dict[str, int] = field(default_factory=dict)
    prevalence_estimates: dict[str, dict[str, float]] = field(default_factory=dict)


def _load_annotations(csv_path: Path) -> list[dict[str, str]]:
    """Load an annotated CSV and return rows."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Annotation CSV not found: {csv_path}")

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    logger.info("Loaded %d annotated instances from %s", len(rows), csv_path)
    return rows


def _interpret_kappa(kappa: float) -> str:
    """Interpret Cohen's kappa using Landis & Koch (1977) scale."""
    if kappa < 0.0:
        return "Poor"
    if kappa < 0.21:
        return "Slight"
    if kappa < 0.41:
        return "Fair"
    if kappa < 0.61:
        return "Moderate"
    if kappa < 0.81:
        return "Substantial"
    return "Almost Perfect"


def compute_audit_statistics(
    rows_a: list[dict[str, str]],
    rows_b: list[dict[str, str]] | None = None,
) -> AuditResults:
    """
    Compute all audit statistics from annotated data.

    Parameters
    ----------
    rows_a : Annotations from annotator A
    rows_b : Annotations from annotator B (optional, for Cohen's κ)
    """
    results = AuditResults()

    # ── Use annotator A as the primary source for precision ────────────
    valid_rows = [r for r in rows_a if r.get("TRUE_POSITIVE", "").strip().upper() in ("Y", "N")]
    results.total_instances = len(valid_rows)

    if results.total_instances == 0:
        logger.error("No valid annotations found! (TRUE_POSITIVE must be Y or N)")
        return results

    # Overall precision
    tp_total = sum(1 for r in valid_rows if r["TRUE_POSITIVE"].strip().upper() == "Y")
    fp_total = results.total_instances - tp_total
    results.overall_precision = tp_total / results.total_instances
    results.overall_ci = clopper_pearson_ci(tp_total, results.total_instances)

    logger.info(
        "Overall: %d/%d = %.1f%% precision [%.1f%%, %.1f%%]",
        tp_total,
        results.total_instances,
        results.overall_precision * 100,
        results.overall_ci[0] * 100,
        results.overall_ci[1] * 100,
    )

    # ── Per-category precision ────────────────────────────────────────
    by_category: dict[str, list[dict[str, str]]] = {}
    for row in valid_rows:
        cat = row.get("category", "unknown")
        by_category.setdefault(cat, []).append(row)

    for cat, cat_rows in sorted(by_category.items()):
        cat_tp = sum(1 for r in cat_rows if r["TRUE_POSITIVE"].strip().upper() == "Y")
        cat_total = len(cat_rows)
        precision = cat_tp / cat_total if cat_total > 0 else 0.0
        ci_low, ci_high = clopper_pearson_ci(cat_tp, cat_total)

        stats = CategoryStats(
            category=cat,
            total=cat_total,
            true_positives=cat_tp,
            false_positives=cat_total - cat_tp,
            precision=precision,
            ci_lower=ci_low,
            ci_upper=ci_high,
        )
        results.per_category.append(stats)

        logger.info(
            "  %-25s %3d/%3d = %.1f%% [%.1f%%, %.1f%%]",
            cat, cat_tp, cat_total, precision * 100, ci_low * 100, ci_high * 100,
        )

    # ── Invented sub-categorization ───────────────────────────────────
    invented_rows = [r for r in valid_rows if r.get("category") == "invented"]
    for row in invented_rows:
        sub = row.get("SUB_CATEGORY", "").strip().lower()
        if sub:
            results.invented_subcategories[sub] = results.invented_subcategories.get(sub, 0) + 1

    if results.invented_subcategories:
        logger.info("Invented sub-categories:")
        for sub, count in sorted(results.invented_subcategories.items(), key=lambda x: -x[1]):
            logger.info("  %-20s %d", sub, count)

    # ── Cohen's kappa (if two annotators) ─────────────────────────────
    if rows_b is not None:
        valid_b = {r.get("id", ""): r for r in rows_b if r.get("TRUE_POSITIVE", "").strip().upper() in ("Y", "N")}
        valid_a = {r.get("id", ""): r for r in rows_a if r.get("TRUE_POSITIVE", "").strip().upper() in ("Y", "N")}

        # Match by ID
        common_ids = sorted(set(valid_a.keys()) & set(valid_b.keys()))
        if common_ids:
            labels_a = [valid_a[i]["TRUE_POSITIVE"].strip().upper() for i in common_ids]
            labels_b = [valid_b[i]["TRUE_POSITIVE"].strip().upper() for i in common_ids]

            results.cohens_kappa = cohens_kappa(labels_a, labels_b)
            results.kappa_interpretation = _interpret_kappa(results.cohens_kappa)

            agreement_count = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
            logger.info(
                "Cohen's κ = %.3f (%s) — %d/%d items agreed",
                results.cohens_kappa,
                results.kappa_interpretation,
                agreement_count,
                len(common_ids),
            )
        else:
            logger.warning("No matching IDs found between annotators")

    # ── Precision-adjusted prevalence per model ───────────────────────
    for json_file in sorted(RESULTS_DIR.glob("progressive_*.json")):
        data = json.loads(json_file.read_text())
        model_name = json_file.stem.replace("progressive_", "")
        summary = data.get("summary", {})
        raw_count = summary.get("total_hallucinations", 0)

        # Per-category adjustment
        cats = summary.get("hallucinations_by_category", {})
        adjusted_count = 0.0
        for cat, count in cats.items():
            # Find the precision for this category from our audit
            cat_precision = results.overall_precision  # fallback
            for cs in results.per_category:
                if cs.category == cat:
                    cat_precision = cs.precision
                    break
            adjusted_count += count * cat_precision

        results.prevalence_estimates[model_name] = {
            "raw_flags": raw_count,
            "adjusted_estimate": round(adjusted_count, 1),
            "adjustment_factor": round(adjusted_count / raw_count, 3) if raw_count > 0 else 0.0,
        }

    return results


def export_results(results: AuditResults, output_path: Path) -> None:
    """Export audit results as JSON for the paper."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "experiment": "expanded_precision_audit",
        "total_instances_audited": results.total_instances,
        "overall_precision": round(results.overall_precision, 4),
        "overall_ci_95": {
            "lower": round(results.overall_ci[0], 4),
            "upper": round(results.overall_ci[1], 4),
        },
        "per_category_precision": [
            {
                "category": cs.category,
                "audited": cs.total,
                "true_positives": cs.true_positives,
                "false_positives": cs.false_positives,
                "precision": round(cs.precision, 4),
                "ci_95_lower": round(cs.ci_lower, 4),
                "ci_95_upper": round(cs.ci_upper, 4),
            }
            for cs in results.per_category
        ],
        "inter_annotator_agreement": {
            "cohens_kappa": round(results.cohens_kappa, 4) if results.cohens_kappa is not None else None,
            "interpretation": results.kappa_interpretation,
        },
        "invented_subcategories": results.invented_subcategories,
        "precision_adjusted_prevalence": results.prevalence_estimates,
    }

    output_path.write_text(json.dumps(report, indent=2))
    logger.info("Exported audit results to %s", output_path)

    # Also print a LaTeX table
    print("\n% ── LaTeX Table: Per-Category Precision ──")
    print("\\begin{table}[!h]")
    print("\\caption{Per-Category Precision from Stratified Manual Audit "
          f"($N={results.total_instances}$)}}")
    print("\\label{tab:precision_audit}")
    print("\\centering")
    print("\\begin{tabular}{|l|c|c|c|c|}")
    print("\\hline")
    print("\\textbf{Category} & \\textbf{Audited} & \\textbf{TP} & "
          "\\textbf{Precision} & \\textbf{95\\% CI} \\\\")
    print("\\hline")
    for cs in results.per_category:
        cat_name = cs.category.replace('_', '\\_')
        print(
            f"{cat_name} & {cs.total} & {cs.true_positives} & "
            f"{cs.precision:.1%} & [{cs.ci_lower:.1%}, {cs.ci_upper:.1%}] \\\\"
        )
        print("\\hline")
    print(f"\\textbf{{Overall}} & \\textbf{{{results.total_instances}}} & "
          f"\\textbf{{{sum(cs.true_positives for cs in results.per_category)}}} & "
          f"\\textbf{{{results.overall_precision:.1%}}} & "
          f"\\textbf{{[{results.overall_ci[0]:.1%}, {results.overall_ci[1]:.1%}]}} \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print("\\end{table}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute audit statistics from annotated CSVs"
    )
    parser.add_argument(
        "--annotator-a",
        type=Path,
        default=OUTPUT_DIR / "audit_annotator_A.csv",
        help="Path to annotator A's filled CSV",
    )
    parser.add_argument(
        "--annotator-b",
        type=Path,
        default=None,
        help="Path to annotator B's filled CSV (optional, for Cohen's κ)",
    )
    args = parser.parse_args()

    rows_a = _load_annotations(args.annotator_a)
    rows_b = _load_annotations(args.annotator_b) if args.annotator_b else None

    results = compute_audit_statistics(rows_a, rows_b)
    export_results(results, OUTPUT_DIR / "audit_statistics.json")

    logger.info("✅ Audit statistics computed and exported!")


if __name__ == "__main__":
    main()
