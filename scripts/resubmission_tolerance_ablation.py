"""
Tolerance Engine Rule Ablation for NeuroAST Resubmission.

Addresses Reviewer 2, Comment 4 (parameter sensitivity / ablation):

    "Please explain how the AST filters, normalization rules, and tolerance
     parameters were selected. Ablation, sensitivity, and cross-dataset
     experiments are needed to exclude CodeNet-specific tuning."

Methodology
-----------
The Tolerance Engine (``src/neuroast/verification/tolerance.py``) contains four
hand-written idiom rules that suppress *valid* C->Java idioms which Phase 1
structural matching would otherwise report as hallucinations:

    R1 ``loop_to_api``     -- for/while loop -> Arrays/Collections API call
    R2 ``memory_model``    -- malloc/calloc/free -> new + garbage collection
    R3 ``string_idiom``    -- char*/strcmp/strcat -> String/.equals()/.concat()
    R4 ``error_handling``  -- return error code -> throw Exception

This script runs six conditions over the full 600-translation corpus:

    * ``all_rules``          -- the published pipeline (all four rules active)
    * ``no_tolerance``       -- raw Phase 1 output (rules disabled entirely)
    * ``minus_<rule>`` (x4)  -- leave-one-out: each rule disabled in turn

For every condition and model we report the number of remaining (reported)
hallucinations. The leave-one-out delta

    additional_flags(rule) = remaining(minus_rule) - remaining(all_rules)

is exactly the number of false flags that rule prevents, which is the
quantity the reviewer asked for.

Phase 1 raw hallucinations are computed **once per pair** and then re-filtered
under each condition, so differences are attributable only to the rule set.
Tolerance matching is deterministic (regex/string based), so these results
contain no model randomness.

Usage:
    uv run python scripts/resubmission_tolerance_ablation.py
    uv run python scripts/resubmission_tolerance_ablation.py --limit 25
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from neuroast.verification.progressive_verifier import ProgressiveVerifier
from neuroast.verification.structures import Hallucination
from neuroast.verification.tolerance import ToleranceEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Per-file tolerance logging would drown the progress output (600 pairs x 6
# conditions). Keep the pipeline quiet; this script logs its own summary.
logging.getLogger("neuroast.verification.tolerance").setLevel(logging.WARNING)

BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_DIR = Path("benchmarks/results")
OUTPUT_FILE = Path("results/resubmission/tolerance_rule_ablation.json")

MODELS = [
    "groq_llama-3.1-8b-instant",
    "groq_llama-3.3-70b-versatile",
    "ollama_llama3.1_8b",
    "ollama_qwen2.5-coder_7b",
]

ALL_RULES = list(ToleranceEngine.ALL_RULES)

RULE_LABELS = {
    "loop_to_api": "Loop $\\rightarrow$ API call",
    "memory_model": "Memory model (\\texttt{malloc}/\\texttt{free})",
    "string_idiom": "String idiom (\\texttt{strcmp}/\\texttt{strcat})",
    "error_handling": "Error handling (return code $\\rightarrow$ exception)",
}


def build_rule_configs(rules: list[str]) -> list[tuple[str, list[str]]]:
    """Build the six ablation conditions: all, none, and leave-one-out."""
    configs: list[tuple[str, list[str]]] = [
        ("all_rules", list(rules)),
        ("no_tolerance", []),
    ]
    for rule in rules:
        configs.append((f"minus_{rule}", [r for r in rules if r != rule]))
    return configs


def apply_conditions(
    hallucinations: list[Hallucination],
    source_code: str,
    target_code: str,
    conditions: list[tuple[ToleranceEngine, str]],
) -> dict[str, int]:
    """Return ``{condition_name: remaining_hallucination_count}``."""
    counts: dict[str, int] = {}
    for engine, name in conditions:
        remaining, _tolerated = engine.apply_tolerance(
            hallucinations,
            source_code=source_code,
            target_code=target_code,
        )
        counts[name] = len(remaining)
    return counts


def run_ablation(models: list[str], limit: int | None = None) -> dict:
    """Compute raw Phase 1 flags once, then re-filter under each condition."""
    verifier = ProgressiveVerifier(mode="structural_only")
    conditions = [
        (ToleranceEngine(enabled_rules=rules), name)
        for name, rules in build_rule_configs(ALL_RULES)
    ]
    condition_names = [name for _engine, name in conditions]

    per_model: dict[str, dict] = {}

    for model in models:
        translations = TRANSLATIONS_DIR / model
        if not translations.exists():
            logger.warning("Skipping %s -- translation directory not found", model)
            continue

        java_files = sorted(translations.glob("*.java"))
        if limit:
            java_files = java_files[:limit]

        raw_total = 0
        remaining_totals = dict.fromkeys(condition_names, 0)
        pairs_scored = 0

        for java_path in java_files:
            source_name = java_path.stem + ".c"
            c_path = BENCHMARKS_DIR / source_name
            if not c_path.exists():
                continue

            try:
                source_code = c_path.read_text(encoding="utf-8", errors="replace")
                target_code = java_path.read_text(encoding="utf-8", errors="replace")
                report = verifier.verify(source_code, target_code)
            except Exception as exc:  # noqa: BLE001 - record and continue
                logger.error("Phase 1 failed for %s/%s: %s", model, source_name, exc)
                continue

            hallucinations = list(report.hallucinations)
            counts = apply_conditions(
                hallucinations, source_code, target_code, conditions
            )

            raw_total += len(hallucinations)
            for name, count in counts.items():
                remaining_totals[name] += count
            pairs_scored += 1

        baseline_remaining = remaining_totals["all_rules"]
        per_model[model] = {
            "files_scored": pairs_scored,
            "raw_phase1_hallucinations": raw_total,
            "conditions": {
                name: {
                    "remaining": remaining_totals[name],
                    "suppressed": raw_total - remaining_totals[name],
                    "suppression_rate": (
                        round((raw_total - remaining_totals[name]) / raw_total, 4)
                        if raw_total
                        else 0.0
                    ),
                    "additional_flags_vs_all_rules": (
                        remaining_totals[name] - baseline_remaining
                    ),
                }
                for name in condition_names
            },
        }

        logger.info(
            "[%s] raw=%d, full pipeline=%d, no tolerance=%d",
            model,
            raw_total,
            baseline_remaining,
            remaining_totals["no_tolerance"],
        )

    aggregate = aggregate_models(per_model, condition_names)
    return {"per_model": per_model, "overall": aggregate}


def aggregate_models(per_model: dict[str, dict], condition_names: list[str]) -> dict:
    """Sum per-model counts into corpus-level totals."""
    raw_total = sum(row["raw_phase1_hallucinations"] for row in per_model.values())
    files_scored = sum(row["files_scored"] for row in per_model.values())

    conditions: dict[str, dict] = {}
    for name in condition_names:
        remaining = sum(
            row["conditions"][name]["remaining"] for row in per_model.values()
        )
        conditions[name] = {
            "remaining": remaining,
            "suppressed": raw_total - remaining,
            "suppression_rate": (
                round((raw_total - remaining) / raw_total, 4) if raw_total else 0.0
            ),
            "additional_flags_vs_all_rules": (
                remaining - conditions["all_rules"]["remaining"]
                if "all_rules" in conditions
                else None
            ),
        }

    return {
        "files_scored": files_scored,
        "raw_phase1_hallucinations": raw_total,
        "conditions": conditions,
    }


def print_latex_table(overall: dict) -> None:
    """Print the leave-one-out ablation table in IEEE Access table style."""
    raw = overall["raw_phase1_hallucinations"]
    conditions = overall["conditions"]

    print("\n% ── LaTeX Table: Tolerance Engine Rule Ablation ──")
    print("\\begin{table}[!t]")
    print(
        "\\caption{Leave-one-out ablation of the four Tolerance Engine rules "
        f"over all {raw} raw Phase-1 structural flags. ``Suppressed'' is the "
        "share of raw flags cleared by the active rule set; ``Extra flags'' "
        "is the increase in reported hallucinations relative to the full "
        "pipeline.}"
    )
    print("\\label{tab:tolerance_ablation}")
    print("\\centering")
    print("\\begin{tabular}{|l|c|c|c|}")
    print("\\hline")
    print(
        "\\textbf{Active rules} & \\textbf{Reported} & "
        "\\textbf{Suppressed (\\%)} & \\textbf{Extra flags} \\\\"
    )
    print("\\hline")

    def row(label: str, name: str) -> None:
        data = conditions[name]
        extra = data["additional_flags_vs_all_rules"]
        extra_cell = "--" if extra is None or name == "all_rules" else f"+{extra}"
        print(
            f"{label} & {data['remaining']} & "
            f"{data['suppression_rate'] * 100:.1f} & {extra_cell} \\\\"
        )

    row("All four rules", "all_rules")
    print("\\hline")
    for rule in ALL_RULES:
        row(f"Without R: {RULE_LABELS[rule]}", f"minus_{rule}")
    print("\\hline")
    row("No tolerance", "no_tolerance")
    print("\\hline")
    print("\\end{tabular}")
    print("\\end{table}")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Leave-one-out ablation of the four Tolerance Engine rules."
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

    logger.info("Running tolerance ablation over models %s", args.models)
    result = run_ablation(args.models, limit=args.limit)
    if not result["per_model"]:
        logger.error("No models evaluated -- nothing to report.")
        return

    output = {
        "experiment": "tolerance_rule_ablation",
        "methodology": (
            "Phase 1 (tree-sitter structural matching) is run once per "
            "translation; the resulting hallucination list is then re-filtered "
            "by six Tolerance Engine configurations (all rules, no rules, and "
            "each single-rule removal). additional_flags_vs_all_rules is the "
            "number of extra reported hallucinations when a rule is removed."
        ),
        "rules": ALL_RULES,
        "rule_labels": RULE_LABELS,
        **result,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2))
    logger.info("Results saved to %s", args.output)

    print_latex_table(result["overall"])


if __name__ == "__main__":
    main()

