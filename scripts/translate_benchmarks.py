"""
Multi-model C → Java translation for NeuroAST benchmarks.

Translates all benchmark C files using multiple LLMs and saves
the Java outputs for ablation evaluation.

Supports:
  - API-based models (Groq, OpenAI, Anthropic) via litellm
  - Ollama models on Colab via ngrok (set OLLAMA_BASE_URL)

Usage:
    python scripts/translate_benchmarks.py                          # all configured models
    python scripts/translate_benchmarks.py --model gpt-4o           # single model
    python scripts/translate_benchmarks.py --ollama-url https://xxx.ngrok-free.dev  # override
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path

from neuroast.neural.translator import Translator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Default model list ──────────────────────────────────────────────────────
# These are the models for the multi-model evaluation (Audit Weakness #2).
# Model strings follow litellm convention: provider/model_name
DEFAULT_MODELS = [
    # "groq/llama-3.3-70b-versatile",    # Open-weights, free via Groq
    # "gpt-4o",                           # Closed-source SOTA
    # Ollama models use the format: ollama/<model_name>
    # Requires OLLAMA_BASE_URL to be set (e.g., ngrok tunnel from Colab)
    "ollama/qwen2.5-coder:7b",         # Open-weights, local/Colab
]


def model_to_dirname(model: str) -> str:
    """Convert a model string to a safe directory name."""
    return model.replace("/", "_").replace(":", "_")


async def translate_model(
    model: str,
    c_files: list[Path],
    output_dir: Path,
    ollama_url: str | None = None,
    rate_limit_delay: float = 1.0,
    concurrency: int = 3,
) -> int:
    """Translate all C files with a single model.
    
    Returns the number of successfully translated files.
    """
    # Set Ollama base URL if this is an Ollama model
    if model.startswith("ollama/") and ollama_url:
        os.environ["OLLAMA_API_BASE"] = ollama_url
        logger.info("Set OLLAMA_API_BASE=%s for %s", ollama_url, model)

    translator = Translator(model=model, temperature=0.1)
    output_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(concurrency)

    async def process_file(i: int, c_file: Path) -> bool:
        async with semaphore:
            java_out_path = output_dir / f"{c_file.stem}.java"

            if java_out_path.exists():
                logger.info("[%d/%d] Skipping %s — already translated", i + 1, len(c_files), c_file.name)
                return True

            logger.info("[%d/%d] Translating %s with %s...", i + 1, len(c_files), c_file.name, model)
            c_code = c_file.read_text()

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    java_code = await translator.translate(c_code)
                    java_out_path.write_text(java_code)
                    logger.info("  ✅ Saved %s", java_out_path.name)
                    await asyncio.sleep(rate_limit_delay)
                    return True
                except Exception as e:
                    logger.error(
                        "  ❌ Failed (attempt %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        str(e)[:200],
                    )
                    if attempt < max_retries - 1:
                        wait = rate_limit_delay * (attempt + 1)
                        logger.info("  Waiting %.1fs before retry...", wait)
                        await asyncio.sleep(wait)
            return False

    tasks = [process_file(i, c_file) for i, c_file in enumerate(c_files)]
    results = await asyncio.gather(*tasks)
    return sum(results)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Translate C benchmarks to Java")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Run only a specific model (e.g., 'gpt-4o')",
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=os.environ.get("OLLAMA_BASE_URL", os.environ.get("OLLAMA_API_BASE", "")),
        help="Ollama base URL (ngrok tunnel from Colab)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.0,
        help="Seconds to wait between API calls (default: 1.0)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent translation requests (default: 3)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=200,
        help="Maximum number of C files to translate (default: 200)",
    )
    args = parser.parse_args()

    benchmarks_dir = Path("benchmarks/datasets")
    results_dir = Path("benchmarks/results")

    c_files = sorted(benchmarks_dir.glob("*.c"))[:args.max_files]
    logger.info("Found %d C files to translate", len(c_files))

    if args.model:
        models = [args.model]
    else:
        models = DEFAULT_MODELS

    # Filter out Ollama models if no URL is set
    active_models = []
    for m in models:
        if m.startswith("ollama/") and not args.ollama_url:
            logger.warning(
                "Skipping %s — no OLLAMA_BASE_URL or --ollama-url set", m
            )
            continue
        active_models.append(m)

    if not active_models:
        logger.error("No models to run. Set OLLAMA_BASE_URL or specify --model")
        return

    logger.info("Models to run: %s", active_models)

    for model in active_models:
        model_dir = results_dir / model_to_dirname(model)
        logger.info("── Translating with %s → %s ──", model, model_dir)

        success = await translate_model(
            model=model,
            c_files=c_files,
            output_dir=model_dir,
            ollama_url=args.ollama_url if model.startswith("ollama/") else None,
            rate_limit_delay=args.rate_limit,
            concurrency=args.concurrency,
        )
        logger.info("✅ %s: %d/%d files translated", model, success, len(c_files))

    logger.info("🎉 All translations complete!")


if __name__ == "__main__":
    asyncio.run(main())
