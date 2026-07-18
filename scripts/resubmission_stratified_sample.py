"""
Expanded Stratified Sampling for Manual Precision Audit.

Addresses Reviewer R1.2 / R2.1 / R2.2:
  - Expands from 50 → 200+ stratified instances
  - Oversamples the dominant "Invented" category
  - Outputs a CSV for TWO independent annotators (for Cohen's κ)
  - Includes the actual C source + Java translation snippets
    so annotators can judge without needing to open files

Usage:
    uv run python scripts/resubmission_stratified_sample.py
    uv run python scripts/resubmission_stratified_sample.py --total 300
    uv run python scripts/resubmission_stratified_sample.py --invented-ratio 0.5
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
RESULTS_DIR = Path("results")
BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_DIR = Path("benchmarks/results")
OUTPUT_DIR = Path("results/resubmission")

# ── Configuration ──────────────────────────────────────────────────────────
STRUCTURAL_CATEGORIES = {"missing", "invented", "depth_mismatch"}
SEMANTIC_CATEGORIES = {
    "lost_control_dep",
    "invalid_type_transform",
    "data_flow_invention",
}


@dataclass
class HallucinationInstance:
    """A single hallucination flag from the progressive results."""

    model: str
    source_file: str
    category: str
    confidence: float
    total_in_file: int
    structural_count: int
    semantic_count: int


def _load_all_hallucinations() -> list[HallucinationInstance]:
    """Load every individual hallucination flag from progressive results."""
    all_instances: list[HallucinationInstance] = []

    for json_file in sorted(RESULTS_DIR.glob("progressive_*.json")):
        data = json.loads(json_file.read_text())
        model_name = json_file.stem.replace("progressive_", "")

        for record in data.get("records", []):
            source_file = record.get("source_file", "")
            categories = record.get("hallucination_categories", {})
            confidence = record.get("final_confidence", 0.0)
            total = record.get("total_hallucinations", 0)
            structural = record.get("structural_hallucinations", 0)
            semantic = record.get("semantic_hallucinations", 0)

            for category, cat_count in categories.items():
                for _ in range(cat_count):
                    all_instances.append(
                        HallucinationInstance(
                            model=model_name,
                            source_file=source_file,
                            category=category,
                            confidence=confidence,
                            total_in_file=total,
                            structural_count=structural,
                            semantic_count=semantic,
                        )
                    )

    return all_instances


def _read_code_snippet(filepath: Path, max_lines: int = 60) -> str:
    """Read source code, truncating to max_lines for the CSV."""
    if not filepath.exists():
        return "[FILE NOT FOUND]"
    lines = filepath.read_text(errors="replace").splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n\n... [{len(lines) - max_lines} more lines truncated]"
    return "\n".join(lines)


def stratified_sample(
    all_instances: list[HallucinationInstance],
    total_count: int,
    invented_ratio: float,
) -> list[HallucinationInstance]:
    """
    Stratified sampling with oversampling of the Invented category.

    Strategy (per R2.2):
      1. Allocate `invented_ratio` of the total budget to Invented
      2. Distribute the remainder proportionally across other categories
      3. Within each category, sample uniformly across models
    """
    # Group by category
    by_category: dict[str, list[HallucinationInstance]] = {}
    for inst in all_instances:
        by_category.setdefault(inst.category, []).append(inst)

    logger.info("Population distribution:")
    for cat, insts in sorted(by_category.items()):
        logger.info("  %-25s %5d (%.1f%%)", cat, len(insts), 100 * len(insts) / len(all_instances))

    # Budget allocation
    invented_budget = int(total_count * invented_ratio)
    remaining_budget = total_count - invented_budget
    other_categories = [c for c in by_category if c != "invented"]
    other_total = sum(len(by_category[c]) for c in other_categories)

    sampled: list[HallucinationInstance] = []

    # Sample Invented (oversampled)
    invented_pool = by_category.get("invented", [])
    n_invented = min(invented_budget, len(invented_pool))
    sampled.extend(random.sample(invented_pool, n_invented))
    logger.info("Sampled %d Invented (budget: %d)", n_invented, invented_budget)

    # Sample remaining categories proportionally
    for cat in other_categories:
        pool = by_category[cat]
        if other_total > 0:
            cat_budget = max(5, int(remaining_budget * len(pool) / other_total))
        else:
            cat_budget = 5
        n_cat = min(cat_budget, len(pool))
        sampled.extend(random.sample(pool, n_cat))
        logger.info("Sampled %d %s (budget: %d)", n_cat, cat, cat_budget)

    random.shuffle(sampled)
    return sampled


def write_annotation_csv(
    sampled: list[HallucinationInstance],
    output_path: Path,
    annotator_id: str,
) -> None:
    """Write a CSV ready for human annotation with code snippets included."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id",
        "annotator",
        "model",
        "source_file",
        "category",
        "confidence",
        "total_in_file",
        "c_source_snippet",
        "java_translation_snippet",
        "TRUE_POSITIVE",
        "SUB_CATEGORY",
        "NOTES",
    ]

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, inst in enumerate(sampled, 1):
            c_path = BENCHMARKS_DIR / inst.source_file
            java_path = TRANSLATIONS_DIR / inst.model / f"{Path(inst.source_file).stem}.java"

            writer.writerow({
                "id": i,
                "annotator": annotator_id,
                "model": inst.model,
                "source_file": inst.source_file,
                "category": inst.category,
                "confidence": round(inst.confidence, 4),
                "total_in_file": inst.total_in_file,
                "c_source_snippet": _read_code_snippet(c_path),
                "java_translation_snippet": _read_code_snippet(java_path),
                "TRUE_POSITIVE": "",  # Annotator fills: Y or N
                "SUB_CATEGORY": "",   # Annotator fills for Invented: try_catch / helper_var / extra_branch / wrapper
                "NOTES": "",
            })

    logger.info("Wrote %d instances to %s", len(sampled), output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate stratified samples for expanded precision audit"
    )
    parser.add_argument(
        "--total", type=int, default=250,
        help="Total number of instances to sample (default: 250)",
    )
    parser.add_argument(
        "--invented-ratio", type=float, default=0.50,
        help="Fraction of budget allocated to Invented category (default: 0.50)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    random.seed(args.seed)

    # Load all hallucination instances
    all_instances = _load_all_hallucinations()
    logger.info("Loaded %d total hallucination instances across all models", len(all_instances))

    # Generate stratified sample
    sampled = stratified_sample(all_instances, args.total, args.invented_ratio)
    logger.info("Final sample size: %d instances", len(sampled))

    # Print sample distribution
    cat_counts: dict[str, int] = {}
    model_counts: dict[str, int] = {}
    for inst in sampled:
        cat_counts[inst.category] = cat_counts.get(inst.category, 0) + 1
        model_counts[inst.model] = model_counts.get(inst.model, 0) + 1

    logger.info("Sample distribution by category:")
    for cat, count in sorted(cat_counts.items()):
        logger.info("  %-25s %5d (%.1f%%)", cat, count, 100 * count / len(sampled))
    logger.info("Sample distribution by model:")
    for model, count in sorted(model_counts.items()):
        logger.info("  %-45s %5d", model, count)

    # Write CSVs for two annotators (identical samples, separate annotation columns)
    write_annotation_csv(
        sampled,
        OUTPUT_DIR / "audit_annotator_A.csv",
        annotator_id="A",
    )
    write_annotation_csv(
        sampled,
        OUTPUT_DIR / "audit_annotator_B.csv",
        annotator_id="B",
    )

    logger.info("✅ Done! Two annotation CSVs written to %s/", OUTPUT_DIR)
    logger.info("Instructions:")
    logger.info("  1. Give audit_annotator_A.csv to Annotator A")
    logger.info("  2. Give audit_annotator_B.csv to Annotator B")
    logger.info("  3. Each annotator fills TRUE_POSITIVE (Y/N) and SUB_CATEGORY for Invented")
    logger.info("  4. Run scripts/resubmission_compute_audit_stats.py to compute statistics")


if __name__ == "__main__":
    main()
