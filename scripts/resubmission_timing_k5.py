"""
Timing Benchmark with k=5 Independent Runs.

Addresses Reviewer R2.4(d) / R3.2:
  - Runs the verification pipeline k=5 times per model per mode
  - Reports mean ± std with medians
  - Resolves the anomaly of Progressive appearing faster than Phase 1 alone
  - Flags Joern-unstable runs separately
  - Produces a clean, reproducible Table 3

Usage:
    uv run python scripts/resubmission_timing_k5.py
    uv run python scripts/resubmission_timing_k5.py --k 3 --model groq_llama-3.3-70b-versatile
    uv run python scripts/resubmission_timing_k5.py --modes structural_only,progressive
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_BASE = Path("benchmarks/results")
OUTPUT_DIR = Path("results/resubmission")


@dataclass
class TimingRecord:
    """Timing data for a single file in a single run."""

    source_file: str
    run_id: int
    time_ms: float
    hallucinations: int
    joern_error: bool = False


@dataclass
class ModelTimingResult:
    """Aggregated timing results for one model × one mode."""

    model: str
    mode: str
    k: int
    per_run_means: list[float] = field(default_factory=list)
    per_run_medians: list[float] = field(default_factory=list)
    per_file_times: list[float] = field(default_factory=list)
    joern_error_count: int = 0
    total_files: int = 0
    total_hallucinations_per_run: list[int] = field(default_factory=list)

    @property
    def grand_mean(self) -> float:
        return statistics.mean(self.per_run_means) if self.per_run_means else 0.0

    @property
    def grand_std(self) -> float:
        return statistics.stdev(self.per_run_means) if len(self.per_run_means) > 1 else 0.0

    @property
    def grand_median(self) -> float:
        return statistics.median(self.per_run_medians) if self.per_run_medians else 0.0


def run_single_pass(
    mode: str,
    model_dir: Path,
    run_id: int,
) -> list[TimingRecord]:
    """
    Run one complete verification pass and collect per-file timing.

    This directly invokes the ProgressiveVerifier rather than shelling out,
    to get precise per-file wall-clock measurements.
    """
    from neuroast.verification.progressive_verifier import ProgressiveVerifier

    c_files = sorted(BENCHMARKS_DIR.glob("*.c"))
    verifier = ProgressiveVerifier(mode=mode)
    records: list[TimingRecord] = []

    for c_file in c_files:
        java_file = model_dir / f"{c_file.stem}.java"
        if not java_file.exists():
            continue

        c_code = c_file.read_text(errors="replace")
        java_code = java_file.read_text(errors="replace")

        joern_error = False
        try:
            wall_start = time.perf_counter()
            report = verifier.verify(c_code, java_code)
            wall_ms = (time.perf_counter() - wall_start) * 1000

            hallucinations = len(report.hallucinations) if hasattr(report, "hallucinations") else 0
            # Fallback: check for total count in different attributes
            if hallucinations == 0:
                for attr in ("structural_hallucinations", "semantic_hallucinations"):
                    hallucinations += getattr(report, attr, 0)
                if hallucinations == 0:
                    # Count from categories
                    cats = getattr(report, "hallucination_categories", {})
                    if isinstance(cats, dict):
                        hallucinations = sum(cats.values())

        except Exception as e:
            wall_ms = (time.perf_counter() - wall_start) * 1000
            hallucinations = 0
            if "joern" in str(e).lower() or "cpg" in str(e).lower():
                joern_error = True
                logger.warning("  Joern error on %s: %s", c_file.name, e)
            else:
                logger.error("  Error on %s: %s", c_file.name, e)

        records.append(TimingRecord(
            source_file=c_file.name,
            run_id=run_id,
            time_ms=wall_ms,
            hallucinations=hallucinations,
            joern_error=joern_error,
        ))

    return records


def run_timing_experiment(
    model_name: str,
    mode: str,
    k: int,
) -> ModelTimingResult:
    """
    Run the verification k times and aggregate timing statistics.
    """
    model_dir = TRANSLATIONS_BASE / model_name
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    result = ModelTimingResult(model=model_name, mode=mode, k=k)
    all_records: list[TimingRecord] = []

    for run in range(1, k + 1):
        logger.info("── Run %d/%d: %s / %s ──", run, k, model_name, mode)
        records = run_single_pass(mode, model_dir, run)
        all_records.extend(records)

        # Per-run stats (excluding Joern errors for clean stats)
        clean_times = [r.time_ms for r in records if not r.joern_error]
        run_mean = statistics.mean(clean_times) if clean_times else 0.0
        run_median = statistics.median(clean_times) if clean_times else 0.0
        run_hallucinations = sum(r.hallucinations for r in records)

        result.per_run_means.append(run_mean)
        result.per_run_medians.append(run_median)
        result.total_hallucinations_per_run.append(run_hallucinations)
        result.total_files = len(records)

        joern_errors = sum(1 for r in records if r.joern_error)
        result.joern_error_count += joern_errors

        logger.info(
            "  Run %d: mean=%.2fms, median=%.2fms, hallucinations=%d, joern_errors=%d",
            run, run_mean, run_median, run_hallucinations, joern_errors,
        )

    result.per_file_times = [r.time_ms for r in all_records if not r.joern_error]

    return result


def export_timing_results(
    all_results: list[ModelTimingResult],
    output_path: Path,
) -> None:
    """Export timing results as JSON and print LaTeX table."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "experiment": "timing_benchmark_k5",
        "results": [],
    }

    for r in all_results:
        report["results"].append({
            "model": r.model,
            "mode": r.mode,
            "k": r.k,
            "total_files_per_run": r.total_files,
            "grand_mean_ms": round(r.grand_mean, 3),
            "grand_std_ms": round(r.grand_std, 3),
            "grand_median_ms": round(r.grand_median, 3),
            "per_run_means_ms": [round(m, 3) for m in r.per_run_means],
            "per_run_medians_ms": [round(m, 3) for m in r.per_run_medians],
            "joern_error_count_total": r.joern_error_count,
            "hallucinations_per_run": r.total_hallucinations_per_run,
        })

    output_path.write_text(json.dumps(report, indent=2))
    logger.info("Exported timing results to %s", output_path)

    # ── Print revised Table 3 ─────────────────────────────────────────
    print("\n% ── LaTeX: Revised Table 3 — Verification Timing (k={} runs) ──".format(
        all_results[0].k if all_results else "?"))
    print("\\begin{table*}[t]")
    k_val = all_results[0].k if all_results else "?"
    print(f"\\caption{{Verification Timing: Mean $\\pm$ Std over $k={k_val}$ Independent Runs}}")
    print("\\label{tab:timing_revised}")
    print("\\centering")
    print("\\begin{tabular}{|l|l|c|c|c|c|c|}")
    print("\\hline")
    print("\\textbf{Model} & \\textbf{Configuration} & \\textbf{Files} & "
          "\\textbf{Hallucinations} & \\textbf{Mean (ms)} & "
          "\\textbf{Std (ms)} & \\textbf{Median (ms)} \\\\")
    print("\\hline")

    # Group by model
    models_seen: set[str] = set()
    for r in all_results:
        model_short = r.model.split("_", 1)[-1] if "_" in r.model else r.model
        prefix = f"\\multirow{{3}}{{*}}{{{model_short}}}" if r.model not in models_seen else ""
        models_seen.add(r.model)

        avg_h = round(statistics.mean(r.total_hallucinations_per_run)) if r.total_hallucinations_per_run else 0
        joern_note = "$^\\dagger$" if r.joern_error_count > 0 else ""

        print(
            f"  {prefix} & {r.mode} & {r.total_files} & {avg_h} & "
            f"{r.grand_mean:.2f}{joern_note} & {r.grand_std:.2f} & "
            f"{r.grand_median:.2f} \\\\"
        )

    print("\\hline")
    print("\\end{tabular}")
    print("\\end{table*}")
    print()

    # ── Verify the timing anomaly ────────────────────────────────────
    print("% ── Timing Anomaly Investigation ──")
    for model_name in {r.model for r in all_results}:
        model_results = {r.mode: r for r in all_results if r.model == model_name}
        p1 = model_results.get("structural_only")
        prog = model_results.get("progressive")
        if p1 and prog:
            diff = prog.grand_mean - p1.grand_mean
            print(f"% {model_name}: P1={p1.grand_mean:.3f}ms, "
                  f"Progressive={prog.grand_mean:.3f}ms, "
                  f"diff={diff:+.3f}ms "
                  f"({'Progressive SLOWER as expected' if diff > 0 else 'Within noise' if abs(diff) < 0.5 else 'ANOMALY'})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run timing benchmark with k independent runs"
    )
    parser.add_argument(
        "--k", type=int, default=5,
        help="Number of independent runs (default: 5)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Run only for a specific model (default: all)",
    )
    parser.add_argument(
        "--modes", type=str, default="structural_only,progressive",
        help="Comma-separated modes to benchmark (default: structural_only,progressive)",
    )
    args = parser.parse_args()

    # Discover models
    if args.model:
        model_names = [args.model]
    else:
        model_names = sorted(
            d.name for d in TRANSLATIONS_BASE.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    modes = [m.strip() for m in args.modes.split(",")]
    logger.info("Models: %s", model_names)
    logger.info("Modes: %s", modes)
    logger.info("k = %d runs per configuration", args.k)

    all_results: list[ModelTimingResult] = []

    for model_name in model_names:
        for mode in modes:
            logger.info("═" * 60)
            logger.info("Starting: %s / %s (k=%d)", model_name, mode, args.k)
            logger.info("═" * 60)
            result = run_timing_experiment(model_name, mode, args.k)
            all_results.append(result)

            logger.info(
                "✓ %s / %s: mean=%.3f ± %.3f ms, median=%.3f ms",
                model_name, mode,
                result.grand_mean, result.grand_std, result.grand_median,
            )

    export_timing_results(all_results, OUTPUT_DIR / "timing_k5_results.json")
    logger.info("✅ Timing benchmark complete!")


if __name__ == "__main__":
    main()
