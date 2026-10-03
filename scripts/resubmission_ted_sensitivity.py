"""
TED Threshold Sensitivity Analysis for NeuroAST Resubmission.

Addresses Reviewer 2, Comment 4 (parameter sensitivity):

    "Please explain how the AST filters, normalization rules, and tolerance
     parameters were selected. Ablation, sensitivity, and cross-dataset
     experiments are needed to exclude CodeNet-specific tuning."

Methodology
-----------
The naive baseline (``scripts/baseline_ted_only.py``) flags a translation as
hallucinated whenever the Zhang-Shasha Tree Edit Distance (TED) between the C
and Java control-flow trees exceeds a threshold ``theta``. The published
baseline uses ``theta = 2``. This script sweeps ``theta in {1, 2, 3, 5}`` and
reports, for every model and every threshold:

  * ``flag_rate``            -- fraction of translations the baseline flags
                                (the quantity reported as the baseline
                                "false positive rate" in Table 6)
  * ``fp_rate_vs_clean``     -- fraction of translations that NeuroAST
                                considers *clean* (zero hallucinations) but
                                that the baseline wrongly flags
  * ``agreement_rate``       -- file-level agreement with NeuroAST's verdict
  * ``miss_rate_vs_flagged`` -- fraction of NeuroAST-flagged files the
                                baseline fails to flag

TED is computed **once per (C, Java) pair** and then re-thresholded, so every
value in a row comes from identical scores -- only ``theta`` varies. This
makes the sweep a true sensitivity analysis rather than four independent runs.

Usage:
    uv run python scripts/resubmission_ted_sensitivity.py
    uv run python scripts/resubmission_ted_sensitivity.py --limit 50
    uv run python scripts/resubmission_ted_sensitivity.py --thresholds 1 2 3 5
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from neuroast.symbolic.extractor import StructuralExtractor
from neuroast.verification.matcher import StructuralMatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_DIR = Path("benchmarks/results")
OUTPUT_FILE = Path("results/resubmission/ted_threshold_sensitivity.json")

# Models to evaluate (matches the four-way ablation in the paper).
MODELS = [
    "groq_llama-3.1-8b-instant",
    "groq_llama-3.3-70b-versatile",
    "ollama_llama3.1_8b",
    "ollama_qwen2.5-coder_7b",
]

# Thresholds requested by the reviewer, plus the published default (theta=2).
DEFAULT_THRESHOLDS = [1, 2, 3, 5]


# ── Data loading ───────────────────────────────────────────────────────────


def load_neuroast_verdicts(model: str) -> dict[str, int]:
    """Load NeuroAST progressive results for *model* as ``{source_file: n}``."""
    path = Path(f"results/progressive_{model}.json")
    if not path.exists():
        logger.warning("NeuroAST results not found for %s (%s)", model, path)
        return {}

    data = json.loads(path.read_text())
    return {
        record.get("source_file", ""): record.get("total_hallucinations", 0)
        for record in data.get("records", [])
    }


def collect_ted_scores(
    models: list[str],
    limit: int | None = None,
) -> dict[str, dict[str, float | None]]:
    """Compute the raw TED score for every (C, Java) pair, once per model.

    Returns
    -------
    dict
        ``{model: {source_file: ted}}`` where ``ted`` is ``None`` when the
        pair could not be parsed.
    """
    c_extractor = StructuralExtractor("c")
    java_extractor = StructuralExtractor("java")
    matcher = StructuralMatcher()

    scores: dict[str, dict[str, float | None]] = {}

    for model in models:
        translations = TRANSLATIONS_DIR / model
        if not translations.exists():
            logger.warning("Skipping %s -- translation directory not found", model)
            continue

        java_files = sorted(translations.glob("*.java"))
        if limit:
            java_files = java_files[:limit]

        model_scores: dict[str, float | None] = {}

        for java_path in java_files:
            source_name = java_path.stem + ".c"
            c_path = BENCHMARKS_DIR / source_name
            if not c_path.exists():
                continue

            try:
                c_config = c_extractor.extract(
                    c_path.read_text(encoding="utf-8", errors="replace")
                )
                java_config = java_extractor.extract(
                    java_path.read_text(encoding="utf-8", errors="replace")
                )
                ted, _similarity = matcher._compute_tree_edit_distance(
                    c_config.functions, java_config.functions
                )
                model_scores[source_name] = float(ted)
            except Exception as exc:  # noqa: BLE001 - record and continue
                logger.error("TED failed for %s/%s: %s", model, source_name, exc)
                model_scores[source_name] = None

        scores[model] = model_scores
        logger.info("[%s] computed TED for %d pairs", model, len(model_scores))

    return scores


# ── Analysis ───────────────────────────────────────────────────────────────


def sweep_threshold(
    ted_scores: dict[str, float | None],
    verdicts: dict[str, int],
    threshold: int,
) -> dict[str, float | int]:
    """Apply a single TED threshold and score it against NeuroAST.

    Parameters
    ----------
    ted_scores:
        ``{source_file: ted}`` for one model.
    verdicts:
        ``{source_file: hallucination_count}`` from NeuroAST.
    threshold:
        Files with ``ted > threshold`` are flagged.
    """
    total = 0
    flagged = 0
    clean_total = 0
    clean_flagged = 0
    flagged_total = 0
    flagged_missed = 0
    agree = 0

    for source_file, ted in ted_scores.items():
        if ted is None:
            continue

        neuroast_flags = verdicts.get(source_file)
        if neuroast_flags is None:
            continue

        baseline_flag = ted > threshold
        neuroast_flag = neuroast_flags > 0

        total += 1
        if baseline_flag:
            flagged += 1
        if not neuroast_flag:
            clean_total += 1
            if baseline_flag:
                clean_flagged += 1
        else:
            flagged_total += 1
            if not baseline_flag:
                flagged_missed += 1
        if baseline_flag == neuroast_flag:
            agree += 1

    return {
        "threshold": threshold,
        "files_scored": total,
        "flagged": flagged,
        "flag_rate": round(flagged / total, 4) if total else 0.0,
        "neuroast_clean_files": clean_total,
        "neuroast_clean_flagged": clean_flagged,
        "fp_rate_vs_clean": round(clean_flagged / clean_total, 4) if clean_total else 0.0,
        "neuroast_flagged_files": flagged_total,
        "missed_by_baseline": flagged_missed,
        "miss_rate_vs_flagged": (
            round(flagged_missed / flagged_total, 4) if flagged_total else 0.0
        ),
        "agreement_rate": round(agree / total, 4) if total else 0.0,
    }


def build_summary(
    ted_scores: dict[str, dict[str, float | None]],
    verdicts: dict[str, dict[str, int]],
    thresholds: list[int],
) -> dict[str, dict]:
    """Sweep every threshold over every model and aggregate across models."""
    per_threshold: dict[str, dict] = {}

    for threshold in thresholds:
        per_model = {
            model: sweep_threshold(scores, verdicts.get(model, {}), threshold)
            for model, scores in ted_scores.items()
        }

        totals = {
            key: sum(row[key] for row in per_model.values())
            for key in (
                "files_scored",
                "flagged",
                "neuroast_clean_files",
                "neuroast_clean_flagged",
                "neuroast_flagged_files",
                "missed_by_baseline",
            )
        }
        agreement_num = sum(
            round(row["agreement_rate"] * row["files_scored"]) for row in per_model.values()
        )
        overall = {
            "threshold": threshold,
            **totals,
            "flag_rate": (
                round(totals["flagged"] / totals["files_scored"], 4)
                if totals["files_scored"]
                else 0.0
            ),
            "fp_rate_vs_clean": (
                round(totals["neuroast_clean_flagged"] / totals["neuroast_clean_files"], 4)
                if totals["neuroast_clean_files"]
                else 0.0
            ),
            "miss_rate_vs_flagged": (
                round(totals["missed_by_baseline"] / totals["neuroast_flagged_files"], 4)
                if totals["neuroast_flagged_files"]
                else 0.0
            ),
            "agreement_rate": (
                round(agreement_num / totals["files_scored"], 4)
                if totals["files_scored"]
                else 0.0
            ),
        }

        per_threshold[str(threshold)] = {"per_model": per_model, "overall": overall}
        logger.info(
            "theta=%d -> overall flag rate %.1f%%, FP vs clean %.1f%%, agreement %.1f%%",
            threshold,
            overall["flag_rate"] * 100,
            overall["fp_rate_vs_clean"] * 100,
            overall["agreement_rate"] * 100,
        )

    return per_threshold


def print_latex_table(per_threshold: dict[str, dict], thresholds: list[int]) -> None:
    """Print the sensitivity table in IEEE Access table style."""
    print("\n% ── LaTeX Table: TED Threshold Sensitivity ──")
    print("\\begin{table}[!t]")
    print(
        "\\caption{Sensitivity of the naive TED baseline to its threshold "
        "$\\theta$. All rates are file-level aggregates over the 600 "
        "translations; ``FP vs.\\ Clean'' counts baseline-flagged files "
        "among translations for which NeuroAST reported zero "
        "hallucinations.}"
    )
    print("\\label{tab:ted_sensitivity}")
    print("\\centering")
    print("\\begin{tabular}{|c|c|c|c|c|}")
    print("\\hline")
    print(
        "$\\theta$ & Flagged (\\%) & FP vs.\\ Clean (\\%) & "
        "Missed (\\%) & Agreement (\\%) \\\\"
    )
    print("\\hline")
    for threshold in thresholds:
        overall = per_threshold[str(threshold)]["overall"]
        print(
            f"{threshold} & {overall['flag_rate'] * 100:.1f} & "
            f"{overall['fp_rate_vs_clean'] * 100:.1f} & "
            f"{overall['miss_rate_vs_flagged'] * 100:.1f} & "
            f"{overall['agreement_rate'] * 100:.1f} \\\\"
        )
    print("\\hline")
    print("\\end{tabular}")
    print("\\end{table}")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep the naive TED baseline threshold and report "
        "false-positive sensitivity."
    )
    parser.add_argument(
        "--thresholds",
        type=int,
        nargs="+",
        default=DEFAULT_THRESHOLDS,
        help=f"TED thresholds to sweep (default: {DEFAULT_THRESHOLDS}).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=MODELS,
        help="Models to evaluate (default: all four ablation models).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit translation files per model (for quick testing).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help=f"Output JSON path (default: {OUTPUT_FILE}).",
    )
    args = parser.parse_args()

    thresholds = sorted(set(args.thresholds))
    logger.info("Sweeping thresholds %s over models %s", thresholds, args.models)

    ted_scores = collect_ted_scores(args.models, limit=args.limit)
    if not ted_scores:
        logger.error("No TED scores computed -- nothing to report.")
        return

    verdicts = {model: load_neuroast_verdicts(model) for model in ted_scores}
    per_threshold = build_summary(ted_scores, verdicts, thresholds)

    output = {
        "experiment": "ted_threshold_sensitivity",
        "methodology": (
            "Zhang-Shasha Tree Edit Distance between C and Java control-flow "
            "trees, thresholded at theta. Scores are computed once per pair "
            "and re-thresholded, so only theta varies across rows. "
            "fp_rate_vs_clean counts baseline-flagged files among the files "
            "for which NeuroAST reported zero hallucinations."
        ),
        "thresholds": thresholds,
        "models": list(ted_scores.keys()),
        "per_threshold": per_threshold,
        "scores": ted_scores,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2))
    logger.info("Results saved to %s", args.output)

    print_latex_table(per_threshold, thresholds)


if __name__ == "__main__":
    main()
