"""
Multi-model ablation benchmark runner for NeuroAST.

Runs the 4-way ablation study (none, structural_only, semantic_only,
progressive) across ALL model translation directories found in
benchmarks/results/. Records real wall-clock timing per file.

Usage:
    python scripts/run_benchmarks.py                    # run all models
    python scripts/run_benchmarks.py --model groq_llama-3.3-70b-versatile  # single model
"""

import argparse
import logging
import time
from pathlib import Path

from neuroast.utils.metrics import MetricsCollector
from neuroast.verification.progressive_verifier import ProgressiveVerifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _purge_joern_before_run() -> None:
    """Purge all Joern workspaces before starting a model run.

    If Joern is unresponsive, restart the Docker container and wait for
    it to become healthy again.
    """
    import contextlib
    import re
    import subprocess
    import time as _time

    try:
        from neuroast.verification.joern_client import JoernClient

        client = JoernClient()
        raw = client.query('workspace.projects.map(_.name).l')
        names = re.findall(r'"([^"]*)"', raw)

        deleted = 0
        for name in names:
            with contextlib.suppress(Exception):
                client.query(f'delete("{name}")')
                deleted += 1

        if names:
            logger.info("Pre-run purge: deleted %d/%d Joern workspaces", deleted, len(names))
        else:
            logger.info("Pre-run purge: Joern workspace is clean")

    except Exception as exc:
        logger.warning("Joern unresponsive (%s) — restarting Docker container...", exc)
        try:
            subprocess.run(
                ["docker", "restart", "neuroast_joern"],
                check=True,
                capture_output=True,
                timeout=30,
            )
            # Wait for Joern to become healthy (healthcheck interval is 15s)
            for attempt in range(12):
                _time.sleep(10)
                result = subprocess.run(
                    ["docker", "inspect", "--format={{.State.Health.Status}}", "neuroast_joern"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if "healthy" in result.stdout:
                    logger.info("Joern restarted and healthy (attempt %d)", attempt + 1)
                    return
            logger.error("Joern failed to become healthy after restart")
        except Exception as restart_exc:
            logger.error("Failed to restart Joern: %s", restart_exc)


def run_experiment(mode: str, model_dir: Path, output_json: Path) -> None:
    """Run a single ablation configuration on one model's translations."""
    benchmarks_dir = Path("benchmarks/datasets")
    c_files = sorted(benchmarks_dir.glob("*.c"))

    # Modes: none, structural_only, semantic_only, progressive
    if mode == "none":
        verifier = None
    else:
        verifier = ProgressiveVerifier(mode=mode)

    collector = MetricsCollector(experiment_name=f"{mode}_{model_dir.name}")

    verified_count = 0
    for c_file in c_files:
        java_file = model_dir / f"{c_file.stem}.java"
        if not java_file.exists():
            continue

        c_code = c_file.read_text()
        java_code = java_file.read_text()

        if verifier:
            logger.info("[%s/%s] Verifying %s...", mode, model_dir.name, c_file.name)
            try:
                # ── TIMING FIX (P0): Wrap verification with wall-clock timer ──
                wall_start = time.perf_counter()
                report = verifier.verify(c_code, java_code)
                wall_elapsed_ms = (time.perf_counter() - wall_start) * 1000

                # Use the internal verification_time_ms if available and non-zero,
                # otherwise fall back to our wall-clock measurement.
                recorded_time_ms = (
                    report.verification_time_ms
                    if report.verification_time_ms > 0.0
                    else wall_elapsed_ms
                )

                collector.add_from_report(
                    report,
                    source_file=c_file.name,
                    model=model_dir.name,
                    total_time_ms=recorded_time_ms,
                )
                verified_count += 1
            except Exception as e:
                logger.error("Error verifying %s: %s", c_file.name, e)
        else:
            # Baseline: no verification, just record a perfectly aligned report
            from neuroast.verification.structures import AlignmentReport

            dummy_report = AlignmentReport(
                is_aligned=True, confidence=1.0, phase="structural"
            )
            collector.add_from_report(
                dummy_report,
                source_file=c_file.name,
                model=model_dir.name,
                total_time_ms=0.0,
            )
            verified_count += 1

    # Export results
    collector.export_json(output_json)

    summary = collector.summarize()
    logger.info(
        "✅ [%s/%s] %d files | %d hallucinations | avg_confidence=%.3f | avg_time=%.1fms",
        mode,
        model_dir.name,
        verified_count,
        summary.total_hallucinations,
        summary.avg_confidence,
        summary.avg_time_ms,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NeuroAST ablation benchmarks")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Run only for a specific model directory name (e.g., groq_llama-3.3-70b-versatile)",
    )
    parser.add_argument(
        "--modes",
        type=str,
        default="none,structural_only,semantic_only,progressive",
        help="Comma-separated list of ablation modes to run",
    )
    args = parser.parse_args()

    results_base = Path("benchmarks/results")
    results_out = Path("results")
    results_out.mkdir(exist_ok=True)

    # Discover all model directories
    if args.model:
        model_dirs = [results_base / args.model]
        if not model_dirs[0].exists():
            logger.error("Model directory not found: %s", model_dirs[0])
            return
    else:
        model_dirs = sorted(
            [d for d in results_base.iterdir() if d.is_dir() and not d.name.startswith(".")]
        )

    if not model_dirs:
        logger.error("No model translation directories found in %s", results_base)
        return

    modes = [m.strip() for m in args.modes.split(",")]
    logger.info("Models: %s", [d.name for d in model_dirs])
    logger.info("Modes: %s", modes)

    for model_dir in model_dirs:
        model_name = model_dir.name
        java_count = len(list(model_dir.glob("*.java")))
        if java_count == 0:
            logger.warning("Skipping %s — no .java files", model_name)
            continue

        logger.info("── Model: %s (%d translations) ──", model_name, java_count)

        for mode in modes:
            out_file = results_out / f"{mode}_{model_name}.json"

            # Purge Joern workspaces before each semantic run to prevent
            # OOM from accumulation across models.
            if mode in ("semantic_only", "progressive"):
                _purge_joern_before_run()

            run_experiment(mode, model_dir, out_file)

    # Also generate combined results for backward compatibility
    # (single-model format matching the original results/)
    if len(model_dirs) == 1:
        model_dir = model_dirs[0]
        for mode in modes:
            compat_file = results_out / f"{mode}.json"
            src_file = results_out / f"{mode}_{model_dir.name}.json"
            if src_file.exists() and not compat_file.exists():
                import shutil
                shutil.copy(src_file, compat_file)

    logger.info("🎉 All experiments complete! Results in %s/", results_out)


if __name__ == "__main__":
    main()
