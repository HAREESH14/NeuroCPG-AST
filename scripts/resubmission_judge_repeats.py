"""
Repeated-Trial LLM-as-a-Judge Experiment for NeuroAST Resubmission.

Addresses Reviewer 2, Comment 6 (LLM-judge comparison fairness):

    "The LLM-judge comparison needs matched prompts, repeated trials, and
     latency and cost reporting. Please also explain whether file-level recall
     is comparable with construct-level symbolic detection."

What this script adds over ``scripts/llm_judge_baseline.py`` and
``scripts/resubmission_independent_judge.py``:

  1. **Matched prompt** -- the judge prompt is imported from
     ``neuroast.neural.prompts.format_judge_prompt`` (the shared, canonical
     template used by every judge experiment in this repository), so the
     self-judge and independent-judge conditions are provably identical
     except for the judge model itself.
  2. **Repeated trials** -- each condition is run k times (default k=3) over
     the same 200-file corpus, and we report mean +/- std, median, min and
     max of the file-level recall, so LLM non-determinism is quantified
     rather than hidden by a single run.
  3. **Latency and cost reporting** -- per-call wall-clock latency and, for
     hosted APIs, the USD cost reported by litellm's cost tracker.

Honesty notes (reported in the output JSON, not silently dropped):
  * Rows whose response could not be parsed are recorded as ``PARSE_ERROR``
    and are *excluded from the recall denominator*; the script additionally
    reports a conservative lower bound that counts them as misses.
  * ``recall_lower_bound_pct`` treats every parse failure as a miss, so
    readers can see the worst case.
  * Recall is file-level (does the judge flag the file at all?) because that
    is the only granularity an LLM judge can produce; NeuroAST's detections
    are construct-level. This mismatch is reported explicitly.

Usage:
    # both conditions, k=3, full 200-file corpus
    uv run python scripts/resubmission_judge_repeats.py

    # quick check
    uv run python scripts/resubmission_judge_repeats.py --limit 5 --trials 1

    # only one condition
    uv run python scripts/resubmission_judge_repeats.py -m ollama/llama3.1:8b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any

import litellm

from neuroast.neural.prompts import format_judge_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# litellm prints a banner/telemetry noise that is not useful in experiment logs.
litellm.suppress_debug_info = True
litellm.telemetry = False

# ── Configuration ──────────────────────────────────────────────────────────
TRANSLATIONS_DIR = Path("benchmarks/results/ollama_llama3.1_8b")
BENCHMARKS_DIR = Path("benchmarks/datasets")
NEUROAST_RESULTS = Path("results/progressive_ollama_llama3.1_8b.json")
OUTPUT_FILE = Path("results/resubmission/judge_repeats_k3.json")

# The translations were produced by this model; using it as the judge is the
# "self-judge" (worst-case Tautology Trap) condition.
TRANSLATOR_MODEL = "ollama/llama3.1:8b"

# Default judge models: (label, model, requires_api_key)
DEFAULT_JUDGE_MODELS = [
    "ollama/llama3.1:8b",  # self-judge
    "gemini/gemini-3.5-flash-lite",  # independent, hosted frontier judge
]

DEFAULT_TRIALS = 3
# Kept deliberately low: hosted free-tier quotas are per-minute, and a burst of
# 429s would otherwise be misreported as judge parse failures.
DEFAULT_CONCURRENCY = 2
DEFAULT_MAX_RETRIES = 3
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Populate ``os.environ`` from ``.env`` without clobbering real env vars."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _extract_json(raw: str) -> dict:
    """Extract a JSON object from raw LLM output.

    Hosted judges frequently wrap the object in markdown fences (observed for
    gemini-2.5-flash), so fences and surrounding prose are stripped
    defensively.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"_parse_failed": True}


# ── Judge call ─────────────────────────────────────────────────────────────


def _completion_kwargs(judge_model: str, ollama_url: str) -> dict[str, Any]:
    """Build provider-specific litellm kwargs for a judge call."""
    kwargs: dict[str, Any] = {"model": judge_model, "timeout": 120}

    if judge_model.startswith("ollama/"):
        kwargs["api_base"] = ollama_url
    elif judge_model.startswith("groq/") and os.environ.get("GROQ_API_KEY"):
        kwargs["api_key"] = os.environ["GROQ_API_KEY"]

    return kwargs


async def judge_translation_async(
    c_code: str,
    java_code: str,
    judge_model: str,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict:
    """Ask a judge model to evaluate one translation.

    Returns a dict with the judge's verdict plus per-call latency and cost.
    A ``hallucinations_found`` of ``-1`` is the parse/API failure sentinel.
    """
    messages = format_judge_prompt(c_code, java_code)
    kwargs = _completion_kwargs(judge_model, ollama_url)

    last_error = ""
    for attempt in range(max_retries + 1):
        started = time.perf_counter()
        try:
            response = await litellm.acompletion(messages=messages, **kwargs)
            latency_ms = (time.perf_counter() - started) * 1000

            raw_content = response.choices[0].message.content or ""
            parsed = _extract_json(raw_content)

            cost_usd: float | None = None
            try:
                cost_usd = float(litellm.completion_cost(response))
            except Exception:  # noqa: BLE001 - local models have no cost entry
                cost_usd = None

            usage = getattr(response, "usage", None)
            tokens = {
                "prompt": getattr(usage, "prompt_tokens", None),
                "completion": getattr(usage, "completion_tokens", None),
                "total": getattr(usage, "total_tokens", None),
            }

            if parsed.get("_parse_failed"):
                return {
                    "hallucinations_found": -1,
                    "is_equivalent": None,
                    "explanation": f"PARSE_FAILED: {raw_content[:300]}",
                    "latency_ms": round(latency_ms, 1),
                    "cost_usd": cost_usd,
                    "tokens": tokens,
                }

            count = parsed.get("hallucinations_found", -1)
            if not isinstance(count, int):
                try:
                    count = int(count)
                except (TypeError, ValueError):
                    count = -1

            return {
                "hallucinations_found": count,
                "is_equivalent": parsed.get("is_equivalent"),
                "explanation": str(parsed.get("explanation", "")),
                "latency_ms": round(latency_ms, 1),
                "cost_usd": cost_usd,
                "tokens": tokens,
            }

        except Exception as exc:  # noqa: BLE001 - record any API failure
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                await asyncio.sleep(_retry_delay(exc, attempt))

    return {
        "hallucinations_found": -1,
        "is_equivalent": None,
        "explanation": f"API_ERROR: {last_error}",
        "latency_ms": None,
        "cost_usd": None,
        "tokens": {"prompt": None, "completion": None, "total": None},
    }


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Backoff seconds for a failed judge call.

    Rate-limit responses (HTTP 429) get a much longer, escalating backoff so
    that hosted free-tier quotas do not silently turn into "parse failures".
    """
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return float(retry_after) + 1.0

    message = str(exc)
    if "429" in message or "RateLimit" in message or "quota" in message.lower():
        return 15.0 * (attempt + 1)
    return 2.0 * (attempt + 1)


def classify(neuroast_count: int, judge_count: int, explanation: str = "") -> str:
    """Classify a judge verdict against NeuroAST's file-level verdict.

    A failed call (``judge_count == -1``) is reported as ``API_ERROR`` when the
    provider call itself failed, and as ``PARSE_ERROR`` when the model replied
    but the response could not be parsed as JSON. The two are kept distinct
    because only the latter is a property of the judge's instruction-following.
    """
    if judge_count == -1:
        return "API_ERROR" if explanation.startswith("API_ERROR") else "PARSE_ERROR"
    neuroast_flagged = neuroast_count > 0
    judge_flagged = judge_count > 0
    if neuroast_flagged and judge_flagged:
        return "AGREE_FLAGGED"
    if neuroast_flagged:
        return "JUDGE_MISSED"
    if judge_flagged:
        return "JUDGE_FALSE_ALARM"
    return "AGREE_CLEAN"


def summarise_trial(records: list[dict]) -> dict:
    """Compute file-level metrics for a single trial."""
    labels = (
        "AGREE_FLAGGED",
        "JUDGE_MISSED",
        "JUDGE_FALSE_ALARM",
        "AGREE_CLEAN",
        "PARSE_ERROR",
        "API_ERROR",
    )
    counts = {
        label: sum(1 for r in records if r["classification"] == label) for label in labels
    }

    total = len(records)
    parse_errors = counts["PARSE_ERROR"]
    api_errors = counts["API_ERROR"]
    parsed = total - parse_errors - api_errors
    neuroast_flagged = counts["AGREE_FLAGGED"] + counts["JUDGE_MISSED"]
    clean_denominator = counts["AGREE_CLEAN"] + counts["JUDGE_FALSE_ALARM"]

    latencies = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    costs = [r["cost_usd"] for r in records if r.get("cost_usd") is not None]

    return {
        "files": total,
        "parsed": parsed,
        "parse_errors": parse_errors,
        "parse_error_rate": round(parse_errors / total, 4) if total else 0.0,
        "api_errors": api_errors,
        "api_error_rate": round(api_errors / total, 4) if total else 0.0,
        "agree_flagged": counts["AGREE_FLAGGED"],
        "judge_missed": counts["JUDGE_MISSED"],
        "judge_false_alarm": counts["JUDGE_FALSE_ALARM"],
        "agree_clean": counts["AGREE_CLEAN"],
        "neuroast_flagged_files": neuroast_flagged,
        # Recall over rows the judge actually answered (failures excluded from
        # the denominator) -- the figure comparable with the paper's Table 5.
        "recall_among_parsed_pct": (
            round(counts["AGREE_FLAGGED"] / neuroast_flagged * 100, 1)
            if neuroast_flagged
            else 0.0
        ),
        # Conservative bound: every unanswered file counted as a miss.
        "recall_lower_bound_pct": (
            round(
                counts["AGREE_FLAGGED"]
                / (
                    counts["AGREE_FLAGGED"]
                    + counts["JUDGE_MISSED"]
                    + parse_errors
                    + api_errors
                )
                * 100,
                1,
            )
            if (neuroast_flagged + parse_errors + api_errors)
            else 0.0
        ),
        "false_alarm_rate_pct": (
            round(counts["JUDGE_FALSE_ALARM"] / clean_denominator * 100, 1)
            if clean_denominator
            else 0.0
        ),
        "latency_mean_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "latency_median_ms": (
            round(statistics.median(latencies), 1) if latencies else None
        ),
        "total_cost_usd": round(sum(costs), 6) if costs else 0.0,
    }


def aggregate_trials(trial_summaries: list[dict]) -> dict:
    """Aggregate per-trial metrics into mean/std/min/max across trials."""
    metrics = (
        "recall_among_parsed_pct",
        "recall_lower_bound_pct",
        "false_alarm_rate_pct",
        "parse_error_rate",
        "api_error_rate",
        "latency_mean_ms",
    )

    aggregate: dict[str, Any] = {"trials": len(trial_summaries)}
    for metric in metrics:
        values = [
            summary[metric]
            for summary in trial_summaries
            if summary.get(metric) is not None
        ]
        if not values:
            aggregate[metric] = None
            continue
        aggregate[metric] = {
            "mean": round(statistics.fmean(values), 2),
            "std": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "median": round(statistics.median(values), 2),
            "per_trial": [round(v, 2) for v in values],
        }

    aggregate["total_cost_usd"] = round(
        sum(s["total_cost_usd"] for s in trial_summaries), 6
    )
    aggregate["false_alarm_per_trial"] = [s["judge_false_alarm"] for s in trial_summaries]
    return aggregate


# ── Runner ─────────────────────────────────────────────────────────────────


def load_neuroast_ground_truth() -> dict[str, int]:
    """Load NeuroAST progressive results as the file-level reference verdict."""
    if not NEUROAST_RESULTS.exists():
        logger.warning("NeuroAST results not found at %s", NEUROAST_RESULTS)
        return {}
    data = json.loads(NEUROAST_RESULTS.read_text())
    return {
        record.get("source_file", ""): record.get("total_hallucinations", 0)
        for record in data.get("records", [])
    }


def _evenly_spaced(items: list, n: int) -> list:
    """Deterministically select *n* items spread evenly across *items*.

    Used to subsample the corpus for conditions that are computationally
    expensive to run (e.g. repeated trials on a CPU-only local judge) while
    still covering the whole corpus instead of only its first few files.
    """
    if n <= 0 or n >= len(items):
        return list(items)
    step = len(items) / n
    indices = sorted({int(i * step) for i in range(n)})
    return [items[i] for i in indices]


def build_pairs(
    limit: int | None = None,
    sample: int | None = None,
) -> list[tuple[str, Path, Path]]:
    """Return ``(source_name, c_path, java_path)`` for every translation pair."""
    pairs: list[tuple[str, Path, Path]] = []
    for c_path in sorted(BENCHMARKS_DIR.glob("*.c")):
        java_path = TRANSLATIONS_DIR / f"{c_path.stem}.java"
        if java_path.exists():
            pairs.append((c_path.name, c_path, java_path))
    if limit:
        pairs = pairs[:limit]
    if sample:
        pairs = _evenly_spaced(pairs, sample)
    return pairs


async def run_condition(
    judge_model: str,
    pairs: list[tuple[str, Path, Path]],
    trials: int,
    concurrency: int,
    ground_truth: dict[str, int],
    ollama_url: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_trial_complete: Any = None,
) -> dict:
    """Run *trials* repetitions of one judge condition over *pairs*."""
    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate(trial: int, source_name: str, c_path: Path, java_path: Path) -> dict:
        async with semaphore:
            c_code = c_path.read_text(encoding="utf-8", errors="replace")
            java_code = java_path.read_text(encoding="utf-8", errors="replace")
            report = await judge_translation_async(
                c_code,
                java_code,
                judge_model,
                ollama_url=ollama_url,
                max_retries=max_retries,
            )

        neuroast_count = ground_truth.get(source_name, 0)
        return {
            "trial": trial,
            "file": source_name,
            "judge_model": judge_model,
            "judge_hallucinations": report["hallucinations_found"],
            "is_equivalent": report["is_equivalent"],
            "neuroast_hallucinations": neuroast_count,
            "classification": classify(
                neuroast_count, report["hallucinations_found"], report["explanation"]
            ),
            "latency_ms": report["latency_ms"],
            "cost_usd": report["cost_usd"],
            # Trimmed to keep the artifact small; full text is not needed for
            # the aggregate metrics.
            "explanation": report["explanation"][:200],
        }

    records: list[dict] = []
    trial_summaries: list[dict] = []

    for trial in range(1, trials + 1):
        completed = 0
        for future in asyncio.as_completed(
            [evaluate(trial, *pair) for pair in pairs]
        ):
            record = await future
            records.append(record)
            completed += 1
            if completed % 25 == 0 or completed == len(pairs):
                logger.info(
                    "[%s] trial %d/%d: %d/%d files judged",
                    judge_model,
                    trial,
                    trials,
                    completed,
                    len(pairs),
                )

        summary = summarise_trial([r for r in records if r["trial"] == trial])
        summary["trial"] = trial
        trial_summaries.append(summary)
        logger.info(
            "[%s] trial %d: recall(parsed) %.1f%%, parse errors %d/%d, "
            "mean latency %s ms, cost $%.4f",
            judge_model,
            trial,
            summary["recall_among_parsed_pct"],
            summary["parse_errors"],
            summary["files"],
            summary["latency_mean_ms"],
            summary["total_cost_usd"],
        )

        if on_trial_complete is not None:
            on_trial_complete(
                {
                    "judge_model": judge_model,
                    "trials": trial_summaries,
                    "aggregate": aggregate_trials(trial_summaries),
                    "records": records,
                }
            )

    return {
        "judge_model": judge_model,
        "is_self_judge": judge_model == TRANSLATOR_MODEL,
        "trials": trial_summaries,
        "aggregate": aggregate_trials(trial_summaries),
        "records": records,
    }


# ── Reporting ──────────────────────────────────────────────────────────────


def _fmt(aggregate: dict, metric: str, digits: int = 1) -> str:
    """Format a ``mean +/- std`` cell from an aggregate block."""
    data = aggregate.get(metric)
    if not data:
        return "--"
    return f"{data['mean']:.{digits}f} $\\pm$ {data['std']:.{digits}f}"


def print_latex_table(conditions: dict[str, dict], trials: int) -> None:
    """Print the repeated-trial comparison in IEEE Access table style."""
    models = list(conditions.keys())

    print("\n% ── LaTeX Table: Repeated-Trial LLM-as-a-Judge Comparison ──")
    print("\\begin{table}[!t]")
    print(
        f"\\caption{{LLM-as-a-Judge comparison over $k={trials}$ repeated trials "
        "on the identical translation corpus and prompt. Recall is file-level; "
        "parse failures are excluded from the recall denominator (lower bounds "
        "that count them as misses appear in the text). NeuroAST reports "
        "construct-level detections and is listed for reference.}"
    )
    print("\\label{tab:judge_repeats}")
    print("\\centering")
    header = " & ".join(
        [
            "\\textbf{Metric}",
            *[
                f"\\textbf{{{model.split('/')[-1]}}}"
                + (" (self)" if conditions[model]["is_self_judge"] else " (indep.)")
                for model in models
            ],
            "\\textbf{NeuroAST}",
        ]
    )
    print("\\begin{tabular}{|l|" + "c|" * (len(models) + 1) + "}")
    print("\\hline")
    print(header + " \\\\")
    print("\\hline")

    rows = [
        ("Trials ($k$)", lambda a: str(a["trials"])),
        ("Recall (\\%)", lambda a: _fmt(a, "recall_among_parsed_pct")),
        ("Recall, lower bd. (\\%)", lambda a: _fmt(a, "recall_lower_bound_pct")),
        (
            "False alarms (per trial)",
            lambda a: "/".join(str(v) for v in a.get("false_alarm_per_trial", [])) or "--",
        ),
        ("Parse failures (\\%)", lambda a: _fmt(a, "parse_error_rate")),
        ("API errors (\\%)", lambda a: _fmt(a, "api_error_rate")),
        ("Latency (ms/file)", lambda a: _fmt(a, "latency_mean_ms", 0)),
        ("Cost, all trials (USD)", lambda a: f"{a.get('total_cost_usd', 0):.4f}"),
    ]
    neuroast_cells = {
        "Trials ($k$)": f"{trials}",
        "Recall (\\%)": "100 (reference)",
        "Recall, lower bd. (\\%)": "100 (reference)",
        "False alarms (per trial)": "0",
        "Parse failures (\\%)": "0",
        "API errors (\\%)": "0",
        "Latency (ms/file)": "2.5",
        "Cost, all trials (USD)": "0.0000",
    }

    for label, extractor in rows:
        cells = [extractor(conditions[model]["aggregate"]) for model in models]
        print(f"{label} & " + " & ".join([*cells, neuroast_cells[label]]) + " \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print("\\end{table}")


def print_console_summary(conditions: dict[str, dict]) -> None:
    """Log a human-readable summary of every condition."""
    for model, result in conditions.items():
        aggregate = result["aggregate"]
        role = "self-judge" if result["is_self_judge"] else "independent judge"
        logger.info("=" * 72)
        logger.info("Judge: %s (%s)", model, role)
        logger.info("=" * 72)
        for summary in result["trials"]:
            logger.info(
                "  trial %d: recall(parsed)=%.1f%%  lower-bound=%.1f%%  "
                "false alarms=%d  parse errors=%d  api errors=%d  (%d files)  "
                "latency=%.0f ms",
                summary["trial"],
                summary["recall_among_parsed_pct"],
                summary["recall_lower_bound_pct"],
                summary["judge_false_alarm"],
                summary["parse_errors"],
                summary.get("api_errors", 0),
                summary["files"],
                summary["latency_mean_ms"] or 0.0,
            )
        recall = aggregate.get("recall_among_parsed_pct") or {}
        logger.info(
            "  => recall(parsed) mean=%.1f%% std=%.1f%% (min %.1f%%, max %.1f%%)",
            recall.get("mean", 0.0),
            recall.get("std", 0.0),
            recall.get("min", 0.0),
            recall.get("max", 0.0),
        )
        logger.info("  => total cost: $%.4f", aggregate.get("total_cost_usd", 0.0))


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run k repeated trials of LLM-as-a-Judge conditions."
    )
    parser.add_argument(
        "--judge-model",
        "-m",
        nargs="+",
        default=DEFAULT_JUDGE_MODELS,
        help=(
            "Judge model(s) in litellm format. The translator model "
            f"({TRANSLATOR_MODEL}) is treated as the self-judge condition. "
            f"Defaults: {DEFAULT_JUDGE_MODELS}"
        ),
    )
    parser.add_argument(
        "--trials",
        "-k",
        type=int,
        default=DEFAULT_TRIALS,
        help=f"Number of repeated trials per condition (default: {DEFAULT_TRIALS}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only judge the first N translation pairs (for quick testing).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help=(
            "Deterministically subsample N pairs spread evenly across the "
            "corpus (use for computationally expensive local judges)."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"In-flight judge calls (default: {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=(
            "Retries per judge call, with rate-limit-aware backoff "
            f"(default: {DEFAULT_MAX_RETRIES})."
        ),
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=os.environ.get("OLLAMA_API_BASE", DEFAULT_OLLAMA_URL),
        help=f"Base URL of the local Ollama server (default: {DEFAULT_OLLAMA_URL}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help=f"Output JSON path (default: {OUTPUT_FILE}).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore results already present in the output file and start over.",
    )
    args = parser.parse_args()

    _load_dotenv()

    ground_truth = load_neuroast_ground_truth()
    pairs = build_pairs(limit=args.limit, sample=args.sample)
    if not pairs:
        logger.error("No translation pairs found -- nothing to judge.")
        return

    logger.info(
        "Judging %d translations, k=%d trials, models=%s",
        len(pairs),
        args.trials,
        args.judge_model,
    )

    experiment: dict[str, Any] = {
        "experiment": "judge_repeats",
        "trials_per_condition": args.trials,
        "translations_judged": len(pairs),
        "translator_model": TRANSLATOR_MODEL,
        "prompt_source": "neuroast.neural.prompts.format_judge_prompt",
        "prompt_is_matched_across_conditions": True,
        "ground_truth_source": str(NEUROAST_RESULTS),
        "granularity_note": (
            "Recall is file-level (does the judge flag the file at all?), the "
            "only granularity an LLM judge can produce. NeuroAST's detections "
            "are construct-level (specific lines and categories), so a file "
            "flagged by the judge as 'containing errors' need not correspond "
            "to the same constructs NeuroAST reports."
        ),
        "conditions": {},
    }

    # Preserve previously completed conditions (e.g. the independent judge run
    # may be executed separately from the local self-judge run) so the final
    # artifact holds every condition side by side.
    if args.output.exists() and not args.fresh:
        try:
            existing = json.loads(args.output.read_text())
            done = existing.get("conditions", {})
            if done:
                experiment["conditions"].update(done)
                logger.info(
                    "Merged existing conditions from %s: %s",
                    args.output,
                    list(done.keys()),
                )
        except json.JSONDecodeError:
            logger.warning("Could not parse existing %s -- starting fresh", args.output)

    def save() -> None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(experiment, indent=2))

    for judge_model in args.judge_model:

        def on_trial(state: dict, model: str = judge_model) -> None:
            experiment["conditions"][model] = state
            save()

        logger.info("── Condition: %s ──", judge_model)
        result = asyncio.run(
            run_condition(
                judge_model=judge_model,
                pairs=pairs,
                trials=args.trials,
                concurrency=args.concurrency,
                ground_truth=ground_truth,
                ollama_url=args.ollama_url,
                max_retries=args.max_retries,
                on_trial_complete=on_trial,
            )
        )
        experiment["conditions"][judge_model] = result
        save()

    logger.info("Results saved to %s", args.output)
    print_console_summary(experiment["conditions"])
    print_latex_table(experiment["conditions"], args.trials)


if __name__ == "__main__":
    main()
