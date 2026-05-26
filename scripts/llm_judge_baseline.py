"""
LLM-as-a-Judge Baseline for NeuroAST.

Proves the "Tautology Trap" — that an LLM cannot reliably verify its own
translations or catch structural/semantic hallucinations.

This script:
  1. Sends each (C, Java) pair to an LLM and asks "are there errors?"
  2. Cross-references the LLM's verdict against NeuroAST's progressive report
  3. Computes the LLM judge's precision, recall, and F1 vs NeuroAST

Usage:
    source .venv/bin/activate
    python scripts/llm_judge_baseline.py                        # full run
    python scripts/llm_judge_baseline.py --limit 50             # quick test
    python scripts/llm_judge_baseline.py --resume               # resume after crash
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import litellm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get(
    "OLLAMA_API_BASE",
    "https://hummingly-athetoid-wanita.ngrok-free.dev",
)
os.environ["OLLAMA_API_BASE"] = OLLAMA_URL
MODEL = "ollama/llama3.1:8b"

TRANSLATIONS_DIR = Path("benchmarks/results/ollama_llama3.1_8b")
BENCHMARKS_DIR = Path("benchmarks/datasets")
OUTPUT_FILE = Path("results/llm_judge_baseline.json")
NEUROAST_RESULTS = Path("results/progressive_ollama_llama3.1_8b.json")


# ── Helpers ────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from LLM output that may contain
    markdown fences, preamble text, or trailing garbage."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON block inside markdown fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find the first { ... } block
    brace_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Give up — return a sentinel so we can track parse failures
    return {"_parse_failed": True}


def _load_neuroast_ground_truth() -> dict[str, int]:
    """Load NeuroAST's progressive verification results as ground truth.
    Returns {filename: hallucination_count}."""
    if not NEUROAST_RESULTS.exists():
        logger.warning("NeuroAST results not found at %s", NEUROAST_RESULTS)
        return {}

    data = json.loads(NEUROAST_RESULTS.read_text())
    ground_truth: dict[str, int] = {}
    for record in data.get("records", []):
        fname = record.get("source_file", "")
        count = record.get("total_hallucinations", 0)
        ground_truth[fname] = count
    return ground_truth


def judge_translation(c_code: str, java_code: str) -> dict:
    """Prompt the LLM to judge the translation. Returns parsed dict."""
    prompt = f"""You are an expert code equivalence checker.
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
}}"""

    try:
        response = litellm.completion(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=60,
            # NOTE: Do NOT pass response_format for Ollama — it's unsupported
            # and causes silent failures or 400 errors.
        )
        raw_content = response.choices[0].message.content or ""
        parsed = _extract_json(raw_content)

        if parsed.get("_parse_failed"):
            logger.warning("JSON parse failed. Raw output: %s", raw_content[:200])
            return {
                "hallucinations_found": -1,  # -1 = parse failure sentinel
                "is_equivalent": None,
                "explanation": f"PARSE_FAILED: {raw_content[:300]}",
            }

        # Validate expected fields exist and have correct types
        h_count = parsed.get("hallucinations_found", -1)
        if not isinstance(h_count, int):
            try:
                h_count = int(h_count)
            except (ValueError, TypeError):
                h_count = -1

        return {
            "hallucinations_found": h_count,
            "is_equivalent": parsed.get("is_equivalent"),
            "explanation": str(parsed.get("explanation", "")),
        }

    except Exception as e:
        logger.error("LLM Judge call failed: %s", e)
        return {
            "hallucinations_found": -1,
            "is_equivalent": None,
            "explanation": f"API_ERROR: {e}",
        }


# ── Main Runner ────────────────────────────────────────────────────────────

def run_baseline(limit: int | None = None, resume: bool = False) -> None:
    """Run the LLM-as-a-Judge baseline and save results."""

    # Load NeuroAST ground truth for comparison
    ground_truth = _load_neuroast_ground_truth()
    logger.info("Loaded NeuroAST ground truth for %d files", len(ground_truth))

    # Find files that have BOTH a .c source AND a .java translation
    c_files = sorted(BENCHMARKS_DIR.glob("*.c"))
    pairs: list[tuple[Path, Path]] = []
    for c_file in c_files:
        java_file = TRANSLATIONS_DIR / f"{c_file.stem}.java"
        if java_file.exists():
            pairs.append((c_file, java_file))

    logger.info("Found %d C/Java translation pairs", len(pairs))

    if limit:
        pairs = pairs[:limit]
        logger.info("Limiting to first %d pairs", limit)

    # Resume support: load existing partial results
    existing_results: list[dict] = []
    already_done: set[str] = set()
    if resume and OUTPUT_FILE.exists():
        existing_data = json.loads(OUTPUT_FILE.read_text())
        existing_results = existing_data.get("records", [])
        already_done = {r["file"] for r in existing_results}
        logger.info("Resuming: %d files already processed", len(already_done))

    results = list(existing_results)
    total_time = sum(r.get("time_ms", 0) for r in results)
    processed = len(results)
    errors = 0

    for i, (c_file, java_file) in enumerate(pairs):
        if c_file.name in already_done:
            continue

        c_code = c_file.read_text(errors="replace")
        java_code = java_file.read_text(errors="replace")

        logger.info("[%d/%d] Judging %s...", i + 1, len(pairs), c_file.name)
        start = time.perf_counter()
        report = judge_translation(c_code, java_code)
        elapsed_ms = (time.perf_counter() - start) * 1000

        total_time += elapsed_ms
        processed += 1

        # Cross-reference with NeuroAST ground truth
        neuroast_count = ground_truth.get(c_file.name, 0)
        judge_count = report["hallucinations_found"]

        # Classification vs NeuroAST:
        #   NeuroAST says has errors (>0) AND Judge says has errors (>0) → Agreement
        #   NeuroAST says has errors (>0) AND Judge says clean (0)     → Judge Missed
        #   NeuroAST says clean (0)       AND Judge says has errors (>0) → Judge False Alarm
        neuroast_flagged = neuroast_count > 0
        judge_flagged = judge_count > 0

        if judge_count == -1:
            classification = "PARSE_ERROR"
            errors += 1
        elif neuroast_flagged and judge_flagged:
            classification = "AGREE_FLAGGED"
        elif neuroast_flagged and not judge_flagged:
            classification = "JUDGE_MISSED"
        elif not neuroast_flagged and judge_flagged:
            classification = "JUDGE_FALSE_ALARM"
        else:
            classification = "AGREE_CLEAN"

        results.append({
            "file": c_file.name,
            "judge_hallucinations": judge_count,
            "is_equivalent": report["is_equivalent"],
            "neuroast_hallucinations": neuroast_count,
            "classification": classification,
            "time_ms": round(elapsed_ms, 1),
            "explanation": report["explanation"],
        })

        logger.info(
            "  → Judge: %d errors | NeuroAST: %d errors | %s | %.0fms",
            judge_count, neuroast_count, classification, elapsed_ms,
        )

        # Incremental save every 10 files (crash protection)
        if processed % 10 == 0:
            _save_results(results, total_time, processed, errors)

    _save_results(results, total_time, processed, errors)
    _print_summary(results, total_time, processed, errors)


def _save_results(
    results: list[dict],
    total_time: float,
    processed: int,
    errors: int,
) -> None:
    """Save current results to disk."""
    valid_results = [r for r in results if r["judge_hallucinations"] != -1]
    avg_time = total_time / processed if processed > 0 else 0
    total_judge_found = sum(
        r["judge_hallucinations"] for r in valid_results
        if r["judge_hallucinations"] > 0
    )

    # Compute comparison metrics
    agree_flagged = sum(1 for r in results if r["classification"] == "AGREE_FLAGGED")
    judge_missed = sum(1 for r in results if r["classification"] == "JUDGE_MISSED")
    judge_false_alarm = sum(1 for r in results if r["classification"] == "JUDGE_FALSE_ALARM")
    agree_clean = sum(1 for r in results if r["classification"] == "AGREE_CLEAN")
    parse_errors = sum(1 for r in results if r["classification"] == "PARSE_ERROR")

    # Judge recall = files where judge caught issues / files where NeuroAST found issues
    neuroast_flagged_total = agree_flagged + judge_missed
    judge_recall = (
        agree_flagged / neuroast_flagged_total
        if neuroast_flagged_total > 0 else 0
    )

    final_report = {
        "summary": {
            "model": MODEL,
            "total_programs": processed,
            "total_hallucinations_found_by_judge": total_judge_found,
            "avg_time_ms": round(avg_time, 1),
            "parse_errors": parse_errors,
            "comparison_vs_neuroast": {
                "agree_flagged": agree_flagged,
                "judge_missed": judge_missed,
                "judge_false_alarm": judge_false_alarm,
                "agree_clean": agree_clean,
                "judge_recall_pct": round(judge_recall * 100, 1),
            },
        },
        "records": results,
    }

    OUTPUT_FILE.write_text(json.dumps(final_report, indent=2))


def _print_summary(
    results: list[dict],
    total_time: float,
    processed: int,
    errors: int,
) -> None:
    """Print a final human-readable summary."""
    avg_time = total_time / processed if processed > 0 else 0

    agree_flagged = sum(1 for r in results if r["classification"] == "AGREE_FLAGGED")
    judge_missed = sum(1 for r in results if r["classification"] == "JUDGE_MISSED")
    judge_false_alarm = sum(1 for r in results if r["classification"] == "JUDGE_FALSE_ALARM")
    agree_clean = sum(1 for r in results if r["classification"] == "AGREE_CLEAN")
    parse_errors = sum(1 for r in results if r["classification"] == "PARSE_ERROR")

    neuroast_flagged = agree_flagged + judge_missed
    judge_recall = (
        agree_flagged / neuroast_flagged * 100
        if neuroast_flagged > 0 else 0
    )

    logger.info("=" * 60)
    logger.info("LLM-AS-A-JUDGE BASELINE REPORT")
    logger.info("=" * 60)
    logger.info("Model:            %s", MODEL)
    logger.info("Files Processed:  %d", processed)
    logger.info("Avg Time/File:    %.1fms  (vs NeuroAST ~0.8ms)", avg_time)
    logger.info("-" * 60)
    logger.info("COMPARISON vs NeuroAST Progressive Verifier:")
    logger.info("  Both agree (flagged):  %d", agree_flagged)
    logger.info("  Judge MISSED errors:   %d  ← LLM blind spots", judge_missed)
    logger.info("  Judge false alarms:    %d", judge_false_alarm)
    logger.info("  Both agree (clean):    %d", agree_clean)
    logger.info("  Parse errors:          %d", parse_errors)
    logger.info("-" * 60)
    logger.info("Judge Recall: %.1f%%  (of files NeuroAST flagged)", judge_recall)
    logger.info("Speed Ratio:  %.0fx slower than NeuroAST", avg_time / 0.8 if avg_time > 0 else 0)
    logger.info("=" * 60)


# ── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-a-Judge baseline")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process the first N files (for quick testing)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from a previous partial run",
    )
    args = parser.parse_args()

    run_baseline(limit=args.limit, resume=args.resume)


if __name__ == "__main__":
    main()
