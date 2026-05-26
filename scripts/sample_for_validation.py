"""
Sample hallucinations for manual precision/recall validation.

Randomly samples N hallucinations from progressive verification results
and outputs a CSV for human annotation.

Usage:
    python scripts/sample_for_validation.py                  # default 30 samples
    python scripts/sample_for_validation.py --count 50       # custom count
    python scripts/sample_for_validation.py --compute-precision results/validation_annotated.csv
"""

import argparse
import csv
import json
import logging
import random
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sample_hallucinations(results_dir: Path, count: int, output_csv: Path) -> None:
    """Sample hallucinations from all progressive results for manual review."""
    all_hallucinations: list[dict] = []

    for json_file in sorted(results_dir.glob("progressive_*.json")):
        data = json.loads(json_file.read_text())
        model_name = json_file.stem.replace("progressive_", "")

        for record in data.get("records", []):
            source_file = record.get("source_file", "")
            categories = record.get("hallucination_categories", {})

            for category, cat_count in categories.items():
                for _ in range(cat_count):
                    all_hallucinations.append({
                        "model": model_name,
                        "source_file": source_file,
                        "category": category,
                        "confidence": record.get("final_confidence", 0),
                        "total_in_file": record.get("total_hallucinations", 0),
                    })

    logger.info("Found %d total hallucinations across all models", len(all_hallucinations))

    if len(all_hallucinations) < count:
        logger.warning(
            "Only %d hallucinations available, sampling all", len(all_hallucinations)
        )
        sampled = all_hallucinations
    else:
        sampled = random.sample(all_hallucinations, count)

    # Write CSV for human annotation
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as f:
        fieldnames = [
            "id", "model", "source_file", "category", "confidence",
            "total_in_file", "TRUE_POSITIVE", "NOTES"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, h in enumerate(sampled, 1):
            writer.writerow({
                "id": i,
                "model": h["model"],
                "source_file": h["source_file"],
                "category": h["category"],
                "confidence": round(h["confidence"], 4),
                "total_in_file": h["total_in_file"],
                "TRUE_POSITIVE": "",   # <-- Human fills this in (Y/N)
                "NOTES": "",           # <-- Human notes
            })

    logger.info(
        "✅ Written %d samples to %s — annotate TRUE_POSITIVE column (Y/N)",
        len(sampled), output_csv,
    )


def compute_precision(annotated_csv: Path) -> None:
    """Compute precision from human-annotated CSV."""
    tp = 0
    fp = 0
    unknown = 0

    with annotated_csv.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            verdict = row.get("TRUE_POSITIVE", "").strip().upper()
            if verdict == "Y":
                tp += 1
            elif verdict == "N":
                fp += 1
            else:
                unknown += 1

    total = tp + fp
    if total == 0:
        logger.error("No annotated rows found (TRUE_POSITIVE must be Y or N)")
        return

    precision = tp / total
    logger.info("=" * 50)
    logger.info("PRECISION REPORT")
    logger.info("=" * 50)
    logger.info("True Positives:  %d", tp)
    logger.info("False Positives: %d", fp)
    logger.info("Unannotated:     %d", unknown)
    logger.info("Precision:       %.1f%% (%d/%d)", precision * 100, tp, total)
    logger.info("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample hallucinations for manual validation"
    )
    parser.add_argument(
        "--count", type=int, default=30,
        help="Number of hallucinations to sample (default: 30)",
    )
    parser.add_argument(
        "--compute-precision", type=str, default=None,
        help="Path to annotated CSV to compute precision",
    )
    args = parser.parse_args()

    if args.compute_precision:
        compute_precision(Path(args.compute_precision))
        return

    results_dir = Path("results")
    output_csv = results_dir / "validation_sample.csv"
    sample_hallucinations(results_dir, args.count, output_csv)


if __name__ == "__main__":
    main()
