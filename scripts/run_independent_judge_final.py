"""
Independent LLM Judge Experiment — Final Run for IEEE Access Resubmission.

Addresses Reviewer 2, Comment 6:
  - Independent judge evaluates Llama-3.1-8B translations
  - k=3 repeated trials with mean ± std reporting
  - Matched prompt (identical to self-judge baseline)
  - Latency and cost reporting
  - Groq primary with OpenRouter fallback (or user-selected models)

Usage:
    uv run python scripts/run_independent_judge_final.py --limit 200
    uv run python scripts/run_independent_judge_final.py --limit 200 --trials 1
    uv run python scripts/run_independent_judge_final.py --check-only
    uv run python scripts/run_independent_judge_final.py --model groq/openai/gpt-oss-120b --limit 200
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True
litellm.telemetry = False

# ── Paths ──────────────────────────────────────────────────────────────────
TRANSLATIONS_DIR = Path("benchmarks/results/ollama_llama3.1_8b")
BENCHMARKS_DIR = Path("benchmarks/datasets")
NEUROAST_RESULTS = Path("results/progressive_ollama_llama3.1_8b.json")
OUTPUT_FILE = Path("results/resubmission/independent_judge_final.json")

# ── Default Models ─────────────────────────────────────────────────────────
DEFAULT_GROQ_MODEL = "groq/llama-3.3-70b-versatile"
DEFAULT_OPENROUTER_MODEL = "openrouter/meta-llama/llama-3.3-70b-instruct:free"

# The model whose translations we're judging (for self-judge detection)
TRANSLATOR_MODEL = "ollama/llama3.1:8b"

DEFAULT_TRIALS = 3
DEFAULT_CONCURRENCY = 1  # sequential to avoid Groq free-tier rate limits
DEFAULT_MAX_RETRIES = 5  # retries for transient rate-limited APIs


# ── Load .env ──────────────────────────────────────────────────────────────

def _load_dotenv(path: Path = Path(".env")) -> None:
    """Populate os.environ from .env without clobbering real env vars."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ── Preflight Model & Key Verification ─────────────────────────────────────

def check_model_ping(model: str) -> tuple[bool, str]:
    """Test model availability with a lightweight single-token completion."""
    try:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            timeout=20,
        )
        content = resp.choices[0].message.content or ""
        return True, f"OK ({content.strip()[:30]})"
    except Exception as exc:
        return False, str(exc)


def run_preflight_checks(models_to_try: list[str]) -> list[str]:
    """Verify models before starting the batch run. Return working models."""
    logger.info("=" * 60)
    logger.info("PREFLIGHT CONNECTIVITY CHECK")
    logger.info("=" * 60)
    working_models: list[str] = []

    for model in models_to_try:
        logger.info("Testing model: %s ...", model)
        ok, reason = check_model_ping(model)
        if ok:
            logger.info("  ✓ %s is AVAILABLE [%s]", model, reason)
            working_models.append(model)
        else:
            lower = reason.lower()
            if "model_not_found" in lower or "does not exist" in lower:
                logger.warning(
                    "  ✗ %s NOT FOUND on provider (model does not exist or tier lacks access).",
                    model,
                )
            elif "decommissioned" in lower:
                logger.warning("  ✗ %s DECOMMISSIONED by provider.", model)
            elif "user not found" in lower or "401" in lower or "authenticationerror" in lower:
                logger.warning(
                    "  ✗ %s AUTHENTICATION FAILED (401: User not found / Invalid API key).",
                    model,
                )
            elif "ratelimit" in lower or "429" in lower or "quota" in lower:
                logger.warning("  ✗ %s RATE LIMITED / QUOTA EXHAUSTED: %s", model, reason[:120])
            else:
                logger.warning("  ✗ %s FAILED: %s", model, reason[:120])

    logger.info("Working models available: %s", working_models or "NONE")
    logger.info("=" * 60)
    return working_models


# ── Judge Prompt (identical to all other judge experiments) ────────────────

JUDGE_USER_PROMPT = """\
You are an expert code equivalence checker.
I have a C program and its Java translation.
Tell me if the Java translation contains any structural hallucinations
(missing loops, invented blocks, wrong nesting) or semantic hallucinations
(broken variables, wrong types, lost control dependencies).

C Source:
```c
{c_code}
```

Java Target:
```java
{java_code}
```

Respond ONLY with a JSON object matching this schema:
{{
    "hallucinations_found": <integer>,
    "is_equivalent": <boolean>,
    "explanation": "<short explanation>"
}}
"""


def format_judge_prompt(c_code: str, java_code: str) -> list[dict[str, str]]:
    """Build the messages list for a judge call."""
    return [
        {
            "role": "user",
            "content": JUDGE_USER_PROMPT.format(c_code=c_code, java_code=java_code),
        }
    ]


# ── JSON Extraction ────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from LLM output."""
    # Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Markdown-fenced JSON
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Greedy brace match (handles nested braces)
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"_parse_failed": True}


# ── Ground Truth ───────────────────────────────────────────────────────────

def load_ground_truth() -> dict[str, int]:
    """Load NeuroAST progressive results as file-level ground truth."""
    if not NEUROAST_RESULTS.exists():
        logger.error("NeuroAST results not found at %s", NEUROAST_RESULTS)
        return {}
    data = json.loads(NEUROAST_RESULTS.read_text())
    return {
        record.get("source_file", ""): record.get("total_hallucinations", 0)
        for record in data.get("records", [])
    }


# ── Judge Call ─────────────────────────────────────────────────────────────

async def judge_one_file(
    c_code: str,
    java_code: str,
    semaphore: asyncio.Semaphore,
    models_to_try: list[str],
    disabled_models: set[str],
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict:
    """Call the judge LLM trying models in order with automatic fallback."""
    messages = format_judge_prompt(c_code, java_code)
    candidate_models = [m for m in models_to_try if m not in disabled_models]

    if not candidate_models:
        return {
            "hallucinations_found": -1,
            "is_equivalent": None,
            "explanation": "API_ERROR: All candidate models are disabled or failed preflight.",
            "latency_ms": None,
            "cost_usd": None,
            "model_used": "none",
        }

    async with semaphore:
        last_error = ""
        for model in candidate_models:
            if model in disabled_models:
                continue

            for attempt in range(max_retries + 1):
                started = time.perf_counter()
                try:
                    kwargs: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "timeout": 120,
                        "temperature": 0.0,  # deterministic for reproducibility
                    }

                    response = await litellm.acompletion(**kwargs)
                    latency_ms = (time.perf_counter() - started) * 1000

                    raw_content = response.choices[0].message.content or ""
                    parsed = _extract_json(raw_content)

                    # Cost tracking
                    cost_usd: float | None = None
                    try:
                        cost_usd = float(litellm.completion_cost(response))
                    except Exception:
                        cost_usd = None

                    if parsed.get("_parse_failed"):
                        return {
                            "hallucinations_found": -1,
                            "is_equivalent": None,
                            "explanation": f"PARSE_FAILED: {raw_content[:300]}",
                            "latency_ms": round(latency_ms, 1),
                            "cost_usd": cost_usd,
                            "model_used": model,
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
                        "explanation": str(parsed.get("explanation", ""))[:200],
                        "latency_ms": round(latency_ms, 1),
                        "cost_usd": cost_usd,
                        "model_used": model,
                    }

                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    msg = str(exc)
                    lower = msg.lower()

                    is_fatal_error = (
                        "401" in msg
                        or "user not found" in lower
                        or "authenticationerror" in lower
                        or "unauthorized" in lower
                        or "invalid_api_key" in lower
                        or "model_not_found" in lower
                        or "does not exist" in lower
                        or "decommissioned" in lower
                        or "404" in msg
                    )

                    is_rate_limit = (
                        "429" in msg
                        or "ratelimit" in lower
                        or "quota" in lower
                        or "rate" in lower
                    )

                    if is_fatal_error:
                        logger.warning(
                            "Fatal error on %s, disabling model and switching: %s",
                            model, msg[:120],
                        )
                        disabled_models.add(model)
                        break  # skip immediately to next model without wasting retries

                    if is_rate_limit:
                        # Rate limit — wait and RETRY on same model
                        retry_after = getattr(exc, "retry_after", None)
                        if isinstance(retry_after, (int, float)) and retry_after > 0:
                            wait = float(retry_after) + 2.0
                        else:
                            wait = min(20.0 * (1.5 ** attempt), 90.0)
                        logger.info(
                            "Rate limited on %s (attempt %d/%d), waiting %.0fs...",
                            model, attempt + 1, max_retries + 1, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        # Other transient error — backoff and retry
                        logger.warning(
                            "Transient error on %s (attempt %d): %s",
                            model, attempt + 1, str(exc)[:100],
                        )
                        await asyncio.sleep(2.0 * (attempt + 1))

        # All models exhausted
        return {
            "hallucinations_found": -1,
            "is_equivalent": None,
            "explanation": f"API_ERROR: {last_error}",
            "latency_ms": None,
            "cost_usd": None,
            "model_used": "none",
        }


# ── Classification ─────────────────────────────────────────────────────────

def classify(neuroast_count: int, judge_count: int, explanation: str = "") -> str:
    """Classify a judge verdict against NeuroAST ground truth."""
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


# ── Summarize ──────────────────────────────────────────────────────────────

def summarise_trial(records: list[dict]) -> dict:
    """Compute file-level metrics for one trial."""
    labels = (
        "AGREE_FLAGGED", "JUDGE_MISSED", "JUDGE_FALSE_ALARM",
        "AGREE_CLEAN", "PARSE_ERROR", "API_ERROR",
    )
    counts = {
        label: sum(1 for r in records if r["classification"] == label)
        for label in labels
    }

    total = len(records)
    parse_errors = counts["PARSE_ERROR"]
    api_errors = counts["API_ERROR"]
    parsed = total - parse_errors - api_errors
    neuroast_flagged = counts["AGREE_FLAGGED"] + counts["JUDGE_MISSED"]
    clean_denominator = counts["AGREE_CLEAN"] + counts["JUDGE_FALSE_ALARM"]

    latencies = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    costs = [r["cost_usd"] for r in records if r.get("cost_usd") is not None]

    # Count which models were used
    model_counts: dict[str, int] = {}
    for r in records:
        m = r.get("model_used", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1

    return {
        "files": total,
        "parsed": parsed,
        "parse_errors": parse_errors,
        "api_errors": api_errors,
        "agree_flagged": counts["AGREE_FLAGGED"],
        "judge_missed": counts["JUDGE_MISSED"],
        "judge_false_alarm": counts["JUDGE_FALSE_ALARM"],
        "agree_clean": counts["AGREE_CLEAN"],
        "neuroast_flagged_files": neuroast_flagged,
        "recall_among_parsed_pct": (
            round(counts["AGREE_FLAGGED"] / neuroast_flagged * 100, 1)
            if neuroast_flagged else 0.0
        ),
        "recall_lower_bound_pct": (
            round(
                counts["AGREE_FLAGGED"]
                / (counts["AGREE_FLAGGED"] + counts["JUDGE_MISSED"]
                   + parse_errors + api_errors)
                * 100, 1,
            )
            if (neuroast_flagged + parse_errors + api_errors) else 0.0
        ),
        "false_alarm_rate_pct": (
            round(counts["JUDGE_FALSE_ALARM"] / clean_denominator * 100, 1)
            if clean_denominator else 0.0
        ),
        "latency_mean_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "latency_median_ms": round(statistics.median(latencies), 1) if latencies else None,
        "total_cost_usd": round(sum(costs), 6) if costs else 0.0,
        "model_usage": model_counts,
    }


def aggregate_trials(trial_summaries: list[dict]) -> dict:
    """Aggregate across k trials into mean/std/min/max."""
    metrics = (
        "recall_among_parsed_pct",
        "recall_lower_bound_pct",
        "false_alarm_rate_pct",
        "latency_mean_ms",
    )
    aggregate: dict[str, Any] = {"trials": len(trial_summaries)}

    for metric in metrics:
        values = [s[metric] for s in trial_summaries if s.get(metric) is not None]
        if not values:
            aggregate[metric] = None
            continue
        aggregate[metric] = {
            "mean": round(statistics.fmean(values), 2),
            "std": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "per_trial": [round(v, 2) for v in values],
        }

    aggregate["total_cost_usd"] = round(
        sum(s["total_cost_usd"] for s in trial_summaries), 6
    )
    aggregate["false_alarm_per_trial"] = [s["judge_false_alarm"] for s in trial_summaries]
    aggregate["total_parse_errors_per_trial"] = [s["parse_errors"] for s in trial_summaries]
    aggregate["total_api_errors_per_trial"] = [s["api_errors"] for s in trial_summaries]
    return aggregate


# ── Build Pairs ────────────────────────────────────────────────────────────

def build_pairs(limit: int | None = 200) -> list[tuple[str, Path, Path]]:
    """Return (source_name, c_path, java_path) for translation pairs up to limit."""
    pairs: list[tuple[str, Path, Path]] = []
    for c_path in sorted(BENCHMARKS_DIR.glob("*.c")):
        java_path = TRANSLATIONS_DIR / f"{c_path.stem}.java"
        if java_path.exists():
            pairs.append((c_path.name, c_path, java_path))
    if limit and limit > 0:
        pairs = pairs[:limit]
    return pairs


# ── Main Runner ────────────────────────────────────────────────────────────

async def run_trials(
    pairs: list[tuple[str, Path, Path]],
    trials: int,
    concurrency: int,
    ground_truth: dict[str, int],
    models_to_try: list[str],
    max_retries: int,
) -> dict:
    """Run k trials of the independent judge over all pairs."""
    semaphore = asyncio.Semaphore(concurrency)
    disabled_models: set[str] = set()

    async def evaluate(trial: int, source_name: str, c_path: Path, java_path: Path) -> dict:
        c_code = c_path.read_text(encoding="utf-8", errors="replace")
        java_code = java_path.read_text(encoding="utf-8", errors="replace")
        report = await judge_one_file(
            c_code=c_code,
            java_code=java_code,
            semaphore=semaphore,
            models_to_try=models_to_try,
            disabled_models=disabled_models,
            max_retries=max_retries,
        )

        neuroast_count = ground_truth.get(source_name, 0)
        return {
            "trial": trial,
            "file": source_name,
            "judge_hallucinations": report["hallucinations_found"],
            "is_equivalent": report["is_equivalent"],
            "neuroast_hallucinations": neuroast_count,
            "classification": classify(
                neuroast_count, report["hallucinations_found"], report.get("explanation", "")
            ),
            "latency_ms": report["latency_ms"],
            "cost_usd": report["cost_usd"],
            "model_used": report["model_used"],
            "explanation": report.get("explanation", "")[:200],
        }

    all_records: list[dict] = []
    trial_summaries: list[dict] = []

    for trial in range(1, trials + 1):
        logger.info("=" * 60)
        logger.info("Starting trial %d/%d (%d files)", trial, trials, len(pairs))
        logger.info("=" * 60)

        completed = 0
        tasks = [evaluate(trial, *pair) for pair in pairs]

        for future in asyncio.as_completed(tasks):
            record = await future
            all_records.append(record)
            completed += 1
            if completed % 10 == 0 or completed == len(pairs):
                logger.info(
                    "  trial %d: %d/%d files judged",
                    trial, completed, len(pairs),
                )

        trial_records = [r for r in all_records if r["trial"] == trial]
        summary = summarise_trial(trial_records)
        summary["trial"] = trial
        trial_summaries.append(summary)

        logger.info(
            "  Trial %d DONE: recall(parsed)=%.1f%%, parse_errors=%d, "
            "api_errors=%d, false_alarms=%d, latency=%.0f ms",
            trial,
            summary["recall_among_parsed_pct"],
            summary["parse_errors"],
            summary["api_errors"],
            summary["judge_false_alarm"],
            summary["latency_mean_ms"] or 0.0,
        )

        # Save after each trial (crash-safe)
        _save_intermediate(trial_summaries, all_records, trials, len(pairs), models_to_try)

    return {
        "judge_models": models_to_try,
        "is_self_judge": False,
        "translator_model": TRANSLATOR_MODEL,
        "trials": trial_summaries,
        "aggregate": aggregate_trials(trial_summaries),
        "records": all_records,
    }


def _save_intermediate(
    trial_summaries: list[dict],
    records: list[dict],
    total_trials: int,
    total_files: int,
    models_to_try: list[str],
) -> None:
    """Save partial results after each trial."""
    experiment = {
        "experiment": "independent_judge_final",
        "judge_models": models_to_try,
        "translator_model": TRANSLATOR_MODEL,
        "translations_judged": total_files,
        "trials_target": total_trials,
        "trials_completed": len(trial_summaries),
        "prompt_source": "Matched judge prompt (identical across all conditions)",
        "granularity_note": (
            "Recall is file-level (does the judge flag the file at all?). "
            "NeuroAST detections are construct-level."
        ),
        "trial_summaries": trial_summaries,
        "aggregate": aggregate_trials(trial_summaries),
        "records": records,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(experiment, indent=2))
    logger.info("Saved intermediate results to %s", OUTPUT_FILE)


# ── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run independent judge over 8B translations (k trials, default limit 200)."
    )
    parser.add_argument(
        "--model", "-m", type=str, default=DEFAULT_GROQ_MODEL,
        help=f"Primary judge model (default: {DEFAULT_GROQ_MODEL})",
    )
    parser.add_argument(
        "--fallback", "-f", type=str, default=DEFAULT_OPENROUTER_MODEL,
        help=f"Fallback judge model (default: {DEFAULT_OPENROUTER_MODEL})",
    )
    parser.add_argument(
        "--trials", "-k", type=int, default=DEFAULT_TRIALS,
        help=f"Number of trials (default: {DEFAULT_TRIALS})",
    )
    parser.add_argument(
        "--limit", type=int, default=200,
        help="Limit to first N files (default: 200)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Concurrent API calls (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
        help=f"Max retries per transient error (default: {DEFAULT_MAX_RETRIES})",
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Run preflight connectivity check and exit without running the full dataset.",
    )
    args = parser.parse_args()

    _load_dotenv()

    groq_key = os.environ.get("GROQ_API_KEY", "")
    or_key = os.environ.get("OPENROUTER_API_KEY", "")

    logger.info("API keys in .env: Groq=%s, OpenRouter=%s",
                "✓" if groq_key else "✗", "✓" if or_key else "✗")

    candidate_models: list[str] = [args.model]
    if args.fallback and args.fallback != args.model:
        candidate_models.append(args.fallback)

    # Preflight check
    working_models = run_preflight_checks(candidate_models)

    if args.check_only:
        logger.info("Check-only mode requested. Exiting.")
        return

    if not working_models:
        logger.error(
            f"\n{'=' * 60}\n"
            f"ERROR: Model '{args.model}' (fallback: '{args.fallback}') cannot be reached!\n\n"
            f"Reasons & How to run Llama 70B:\n"
            f"1. OpenRouter (Recommended for Llama 3.3 70B):\n"
            f"   - Model: 'openrouter/meta-llama/llama-3.3-70b-instruct'\n"
            f"   - Current issue: OPENROUTER_API_KEY in .env returned 401 (User not found).\n"
            f"   - Fix: Get an active key from https://openrouter.ai/keys and update .env.\n\n"
            f"2. Groq:\n"
            f"   - Current issue: Groq officially decommissioned llama-3.3-70b-versatile\n"
            f"     from developer/free tiers on August 16, 2026.\n"
            f"   - Groq currently has no public Llama 70B endpoints on your tier.\n"
            f"{'=' * 60}"
        )
        return

    ground_truth = load_ground_truth()
    if not ground_truth:
        logger.error("No ground truth loaded — aborting")
        return

    pairs = build_pairs(limit=args.limit)
    if not pairs:
        logger.error("No translation pairs found")
        return

    logger.info(
        "Independent Judge Experiment: %d files × %d trials = %d calls",
        len(pairs), args.trials, len(pairs) * args.trials,
    )
    logger.info("Active Models: %s", working_models)

    result = asyncio.run(
        run_trials(
            pairs=pairs,
            trials=args.trials,
            concurrency=args.concurrency,
            ground_truth=ground_truth,
            models_to_try=working_models,
            max_retries=args.max_retries,
        )
    )

    # Final summary
    agg = result["aggregate"]
    recall = agg.get("recall_among_parsed_pct", {})
    logger.info("=" * 60)
    logger.info("FINAL RESULTS")
    logger.info("=" * 60)
    logger.info(
        "Recall (parsed): mean=%.1f%% ± %.1f%% (min=%.1f%%, max=%.1f%%)",
        recall.get("mean", 0), recall.get("std", 0),
        recall.get("min", 0), recall.get("max", 0),
    )
    logger.info(
        "Parse errors per trial: %s",
        agg.get("total_parse_errors_per_trial", []),
    )
    logger.info(
        "False alarms per trial: %s",
        agg.get("false_alarm_per_trial", []),
    )
    lat = agg.get("latency_mean_ms", {})
    if isinstance(lat, dict):
        logger.info("Latency: mean=%.0f ms", lat.get("mean", 0))
    logger.info("Total cost: $%.4f", agg.get("total_cost_usd", 0))
    logger.info("Results saved to %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
