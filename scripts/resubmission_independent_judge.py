"""
Independent LLM Judge Experiment for NeuroAST Resubmission.

Addresses Reviewer R2.4(b) / R3.3:
  - Uses an INDEPENDENT, stronger model (Llama-3.3-70B) to judge
    the 8B model's translations — not self-judging
  - Uses the IDENTICAL protocol as the original llm_judge_baseline.py
  - Retains the original self-judging as the "worst case" condition
  - Reports both conditions in a comparative table

Usage:
    uv run python scripts/resubmission_independent_judge.py                     # full run
    uv run python scripts/resubmission_independent_judge.py --limit 20          # quick test
    uv run python scripts/resubmission_independent_judge.py --resume            # resume
    uv run python scripts/resubmission_independent_judge.py -m groq/llama-3.3-70b-versatile
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import litellm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
# The translations being judged are from the 8B model
TRANSLATIONS_DIR = Path("benchmarks/results/ollama_llama3.1_8b")
BENCHMARKS_DIR = Path("benchmarks/datasets")
NEUROAST_RESULTS = Path("results/progressive_ollama_llama3.1_8b.json")
OUTPUT_DIR = Path("results/resubmission")

# Supported models including NVIDIA NIM models and Ollama Colab models.
# NVIDIA NIM models may be passed either as the raw model id (with --nvidia-url
# and --nvidia-key) or with the nvidia_nim/ provider prefix.
SUPPORTED_JUDGE_MODELS = [
    "meta/llama-3.3-70b-instruct",  # NVIDIA NIM (Llama 3.3 70B) — raw model id
    "nvidia_nim/meta/llama-3.3-70b-instruct",  # NVIDIA NIM provider prefix
    "ollama/llama3.1:8b",  # Ollama Colab (Llama 3.1 8B)
    "ollama/qwen2.5-coder:7b",  # Ollama Colab (Qwen 2.5 Coder 7B)
    "groq/llama-3.3-70b-versatile",  # Groq Cloud (Llama 3.3 70B)
]

# Default judge model — a DIFFERENT, stronger model than the translator.
# Runs against the NVIDIA NIM endpoint by default.
DEFAULT_JUDGE_MODEL = "meta/llama-3.3-70b-instruct"

# API config
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# NVIDIA NIM API config
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", os.environ.get("NVIDIA_NIM_API_KEY", ""))
if NVIDIA_API_KEY:
    os.environ["NVIDIA_API_KEY"] = NVIDIA_API_KEY
    os.environ["NVIDIA_NIM_API_KEY"] = NVIDIA_API_KEY
NVIDIA_API_BASE = os.environ.get("NVIDIA_API_BASE", "https://integrate.api.nvidia.com/v1")

# Ollama API config (e.g., running on Google Colab via ngrok)
OLLAMA_URL = os.environ.get(
    "OLLAMA_API_BASE",
    "https://hummingly-athetoid-wanita.ngrok-free.dev",
)
os.environ["OLLAMA_API_BASE"] = OLLAMA_URL


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from LLM output."""
    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try markdown-fenced JSON
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try first {...} block
    brace_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"_parse_failed": True}


def _safe_model_name(model: str) -> str:
    """Convert a model string to a safe directory/file name."""
    return model.replace("/", "_").replace(":", "_")


def _load_neuroast_ground_truth() -> dict[str, int]:
    """Load NeuroAST progressive results as ground truth."""
    if not NEUROAST_RESULTS.exists():
        logger.warning("NeuroAST results not found at %s", NEUROAST_RESULTS)
        return {}
    data = json.loads(NEUROAST_RESULTS.read_text())
    return {
        r.get("source_file", ""): r.get("total_hallucinations", 0) for r in data.get("records", [])
    }


def judge_translation(
    c_code: str,
    java_code: str,
    judge_model: str,
    ollama_url: str | None = None,
    nvidia_url: str | None = None,
    nvidia_key: str | None = None,
) -> dict:
    """
    Prompt a judge model to evaluate a translation.

    Uses the IDENTICAL prompt as the original llm_judge_baseline.py
    for a fair comparison.
    """
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
        completion_kwargs: dict[str, Any] = {
            "model": judge_model,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": 120,
        }

        # Configure API base/key dynamically depending on provider prefix or model name
        is_nvidia = (
            judge_model.startswith("nvidia_nim/")
            or judge_model.startswith("nvidia/")
            or judge_model == "meta/llama-3.3-70b-instruct"
        )
        if is_nvidia:
            base = nvidia_url or NVIDIA_API_BASE
            if base:
                completion_kwargs["api_base"] = base
            key = (
                nvidia_key
                or os.environ.get("NVIDIA_API_KEY")
                or os.environ.get("NVIDIA_NIM_API_KEY")
            )
            if key:
                completion_kwargs["api_key"] = key
            # If the user passed the raw NVIDIA model id without a provider prefix,
            # litellm needs the nvidia_nim/ prefix to route correctly.
            if judge_model == "meta/llama-3.3-70b-instruct":
                completion_kwargs["model"] = f"nvidia_nim/{judge_model}"
        elif judge_model.startswith("ollama/") or judge_model in (
            "llama3.1:8b",
            "qwen2.5-coder:7b",
        ):
            if not judge_model.startswith("ollama/"):
                completion_kwargs["model"] = f"ollama/{judge_model}"
            base_url = ollama_url or os.environ.get("OLLAMA_API_BASE", OLLAMA_URL)
            if base_url:
                completion_kwargs["api_base"] = base_url
                os.environ["OLLAMA_API_BASE"] = base_url
                if "ngrok" in base_url:
                    completion_kwargs["extra_headers"] = {"ngrok-skip-browser-warning": "true"}
        elif judge_model.startswith("groq/"):
            if os.environ.get("GROQ_API_KEY"):
                completion_kwargs["api_key"] = os.environ.get("GROQ_API_KEY")

        response = litellm.completion(**completion_kwargs)
        raw_content = response.choices[0].message.content or ""
        parsed = _extract_json(raw_content)

        if parsed.get("_parse_failed"):
            logger.warning("JSON parse failed. Raw: %s", raw_content[:200])
            return {
                "hallucinations_found": -1,
                "is_equivalent": None,
                "explanation": f"PARSE_FAILED: {raw_content[:300]}",
            }

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


def _classify(
    neuroast_count: int,
    judge_count: int,
) -> str:
    """Classify agreement between judge and NeuroAST."""
    if judge_count == -1:
        return "PARSE_ERROR"
    neuroast_flagged = neuroast_count > 0
    judge_flagged = judge_count > 0
    if neuroast_flagged and judge_flagged:
        return "AGREE_FLAGGED"
    if neuroast_flagged and not judge_flagged:
        return "JUDGE_MISSED"
    if not neuroast_flagged and judge_flagged:
        return "JUDGE_FALSE_ALARM"
    return "AGREE_CLEAN"


def run_independent_judge(
    judge_model: str,
    limit: int | None = None,
    resume: bool = False,
    ollama_url: str | None = None,
    nvidia_url: str | None = None,
    nvidia_key: str | None = None,
) -> None:
    """Run the independent judge experiment."""
    output_file = OUTPUT_DIR / f"independent_judge_{_safe_model_name(judge_model)}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    ground_truth = _load_neuroast_ground_truth()
    logger.info("Loaded NeuroAST ground truth for %d files", len(ground_truth))

    # Find translation pairs
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

    # Resume support
    existing_results: list[dict] = []
    already_done: set[str] = set()
    if resume and output_file.exists():
        existing_data = json.loads(output_file.read_text())
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

        logger.info(
            "[%d/%d] Judge (%s) evaluating %s...",
            i + 1,
            len(pairs),
            judge_model,
            c_file.name,
        )
        start = time.perf_counter()
        report = judge_translation(
            c_code,
            java_code,
            judge_model,
            ollama_url=ollama_url,
            nvidia_url=nvidia_url,
            nvidia_key=nvidia_key,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        total_time += elapsed_ms
        processed += 1

        neuroast_count = ground_truth.get(c_file.name, 0)
        judge_count = report["hallucinations_found"]
        classification = _classify(neuroast_count, judge_count)

        if classification == "PARSE_ERROR":
            errors += 1
            exp = report["explanation"]
            if "AuthenticationError" in exp or ("401" in exp and "Authentication failed" in exp):
                logger.error(
                    "❌ Authentication error (401 Unauthorized) detected while evaluating with %s.",
                    judge_model,
                )
                logger.error(
                    "❌ Aborting early to avoid repeating authentication errors on all files."
                )
                logger.error(
                    "📌 TIP: Pass your API key (e.g. 'nvapi-...') to --nvidia-key, NOT a URL!"
                )
                break

        results.append(
            {
                "file": c_file.name,
                "judge_model": judge_model,
                "judge_hallucinations": judge_count,
                "is_equivalent": report["is_equivalent"],
                "neuroast_hallucinations": neuroast_count,
                "classification": classification,
                "time_ms": round(elapsed_ms, 1),
                "explanation": report["explanation"],
            }
        )

        logger.info(
            "  → Judge: %d errors | NeuroAST: %d | %s | %.0fms",
            judge_count,
            neuroast_count,
            classification,
            elapsed_ms,
        )

        # Incremental save every 10 files
        if processed % 10 == 0:
            _save_results(results, judge_model, total_time, processed, errors, output_file)

    _save_results(results, judge_model, total_time, processed, errors, output_file)
    _print_comparative_summary(judge_model, output_file)


def _save_results(
    results: list[dict],
    judge_model: str,
    total_time: float,
    processed: int,
    errors: int,
    output_file: Path,
) -> None:
    """Save current results."""
    agree_flagged = sum(1 for r in results if r["classification"] == "AGREE_FLAGGED")
    judge_missed = sum(1 for r in results if r["classification"] == "JUDGE_MISSED")
    judge_false_alarm = sum(1 for r in results if r["classification"] == "JUDGE_FALSE_ALARM")
    agree_clean = sum(1 for r in results if r["classification"] == "AGREE_CLEAN")
    parse_errors = sum(1 for r in results if r["classification"] == "PARSE_ERROR")

    neuroast_flagged_total = agree_flagged + judge_missed
    judge_recall = agree_flagged / neuroast_flagged_total if neuroast_flagged_total > 0 else 0

    valid_results = [r for r in results if r["judge_hallucinations"] != -1]
    total_judge_found = sum(
        r["judge_hallucinations"] for r in valid_results if r["judge_hallucinations"] > 0
    )

    report = {
        "experiment": "independent_judge",
        "judge_model": judge_model,
        "translator_model": "ollama/llama3.1:8b",
        "summary": {
            "total_programs": processed,
            "total_hallucinations_found_by_judge": total_judge_found,
            "avg_time_ms": round(total_time / processed, 1) if processed > 0 else 0,
            "parse_errors": parse_errors,
            "parse_error_rate": round(parse_errors / processed, 3) if processed > 0 else 0,
            "comparison_vs_neuroast": {
                "agree_flagged": agree_flagged,
                "judge_missed": judge_missed,
                "judge_false_alarm": judge_false_alarm,
                "agree_clean": agree_clean,
                "judge_recall_pct": round(judge_recall * 100, 1),
                "judge_recall_excl_parse_errors": round(
                    agree_flagged / (agree_flagged + judge_missed) * 100, 1
                )
                if (agree_flagged + judge_missed) > 0
                else 0,
            },
        },
        "records": results,
    }

    output_file.write_text(json.dumps(report, indent=2))


def _print_comparative_summary(judge_model: str, output_file: Path) -> None:
    """Print comparison between independent judge and original self-judge."""
    independent = json.loads(output_file.read_text())

    # Load original self-judge results
    original_path = Path("results/llm_judge_baseline.json")
    original = json.loads(original_path.read_text()) if original_path.exists() else None

    logger.info("=" * 70)
    logger.info("INDEPENDENT JUDGE EXPERIMENT — COMPARATIVE RESULTS")
    logger.info("=" * 70)

    ind_summary = independent["summary"]
    ind_comp = ind_summary["comparison_vs_neuroast"]

    logger.info("Independent Judge (%s):", judge_model)
    logger.info("  Recall (file-level):     %.1f%%", ind_comp["judge_recall_pct"])
    logger.info("  Recall (excl. parse):    %.1f%%", ind_comp["judge_recall_excl_parse_errors"])
    logger.info(
        "  Parse errors:            %d/%d (%.1f%%)",
        ind_summary["parse_errors"],
        ind_summary["total_programs"],
        ind_summary["parse_error_rate"] * 100,
    )
    logger.info("  Avg time/file:           %.1f ms", ind_summary["avg_time_ms"])

    if original:
        orig_summary = original["summary"]
        orig_comp = orig_summary["comparison_vs_neuroast"]
        logger.info("")
        logger.info("Original Self-Judge (ollama/llama3.1:8b):")
        logger.info("  Recall (file-level):     %.1f%%", orig_comp["judge_recall_pct"])
        logger.info(
            "  Parse errors:            %d/%d",
            orig_summary["parse_errors"],
            orig_summary["total_programs"],
        )
        logger.info("  Avg time/file:           %.1f ms", orig_summary["avg_time_ms"])

    logger.info("-" * 70)
    logger.info("NeuroAST Progressive (reference):")
    logger.info("  Recall:                  100%% (by definition — it is the reference)")
    logger.info("  Avg time/file:           ~2.5 ms")
    logger.info("=" * 70)

    # Print LaTeX table
    print("\n% ── LaTeX Table: Judge Comparison ──")
    print("\\begin{table}[!h]")
    print("\\caption{LLM-as-a-Judge: Self-Judging vs Independent Judge}")
    print("\\label{tab:judge_comparison}")
    print("\\centering")
    print("\\begin{tabular}{|l|c|c|c|}")
    print("\\hline")
    print(
        "\\textbf{Metric} & \\textbf{Self-Judge (8B)} & "
        f"\\textbf{{Independent ({judge_model.split('/')[-1]})}} & "
        "\\textbf{NeuroAST} \\\\"
    )
    print("\\hline")

    if original:
        orig_comp = original["summary"]["comparison_vs_neuroast"]
        print(
            f"File-Level Recall & {orig_comp['judge_recall_pct']:.1f}\\% & "
            f"{ind_comp['judge_recall_pct']:.1f}\\% & 100\\% \\\\"
        )
        print("\\hline")
        print(
            f"Parse Errors & {original['summary']['parse_errors']} & "
            f"{ind_summary['parse_errors']} & 0 \\\\"
        )
        print("\\hline")
        print(
            f"Avg Latency (ms) & {original['summary']['avg_time_ms']:.0f} & "
            f"{ind_summary['avg_time_ms']:.0f} & 2.5 \\\\"
        )
        print("\\hline")

    print("\\end{tabular}")
    print("\\end{table}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent LLM judge experiment")
    parser.add_argument(
        "--judge-model",
        "-m",
        type=str,
        default=DEFAULT_JUDGE_MODEL,
        help=f"Model to use as judge (default: {DEFAULT_JUDGE_MODEL})",
    )
    supported_str = ", ".join(SUPPORTED_JUDGE_MODELS)
    parser.add_argument(
        "--models",
        nargs="+",
        type=str,
        default=None,
        help=f"Multiple models to evaluate sequentially. Supported options: {supported_str}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N files",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous partial run",
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=os.environ.get("OLLAMA_API_BASE", OLLAMA_URL),
        help="Base URL for Ollama API (e.g., ngrok URL from Google Colab)",
    )
    parser.add_argument(
        "--nvidia-url",
        type=str,
        default=os.environ.get("NVIDIA_API_BASE", NVIDIA_API_BASE),
        help="Base URL for NVIDIA NIM API",
    )
    parser.add_argument(
        "--nvidia-key",
        type=str,
        default=os.environ.get("NVIDIA_API_KEY", ""),
        help="API key for NVIDIA NIM API",
    )
    args = parser.parse_args()

    if args.nvidia_key and (
        args.nvidia_key.startswith("http://") or args.nvidia_key.startswith("https://")
    ):
        raise ValueError(
            f"\n\n❌ ERROR: You passed a URL ('{args.nvidia_key}') to --nvidia-key!\n"
            f"Please pass your API base URL to --nvidia-url (or let it default to "
            f"'{NVIDIA_API_BASE}'), and pass your actual NVIDIA API key (which starts "
            f"with 'nvapi-') to --nvidia-key.\n\n"
            "Correct Usage Example:\n"
            '  uv run python scripts/resubmission_independent_judge.py --nvidia-key "nvapi-..." '
            "--limit 200\n"
        )

    models_to_run = args.models if args.models else [args.judge_model]

    logger.info("Models to judge: %s", models_to_run)
    logger.info("Translator:      ollama/llama3.1:8b")
    logger.info("This is an INDEPENDENT judge — NOT self-judging")

    for model in models_to_run:
        logger.info("── Running evaluation with judge model: %s ──", model)
        run_independent_judge(
            judge_model=model,
            limit=args.limit,
            resume=args.resume,
            ollama_url=args.ollama_url,
            nvidia_url=args.nvidia_url,
            nvidia_key=args.nvidia_key,
        )

    logger.info("✅ Independent judge experiment complete for all selected models!")


if __name__ == "__main__":
    main()


