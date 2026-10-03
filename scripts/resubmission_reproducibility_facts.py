"""
Reproducibility Fact Sheet for NeuroAST Resubmission.

Addresses Reviewer 2, Comment 2 (experimental reproducibility):

    "Please report the language pairs, translation directions, CodeNet sampling
     procedure, exact model versions, prompts, decoding settings, parsing
     failures, and definitions of the five hallucination categories."

Rather than hand-transcribing these details into the manuscript (where they
drift out of sync with the code), this script extracts them programmatically:

  * translation prompt text      -- imported from ``neuroast.neural.prompts``
  * judge prompt text            -- imported from ``neuroast.neural.prompts``
  * decoding settings            -- read from the experiment entry points
  * exact model identifiers      -- the litellm strings that name each model
  * tree-sitter parse failures   -- recomputed over every stored translation
                                    with the *same* parsers the pipeline uses
  * library versions + commit    -- for environment-level reproducibility

Output: ``results/resubmission/reproducibility_details.json``

Usage:
    uv run python scripts/resubmission_reproducibility_facts.py
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import subprocess
import sys
from pathlib import Path

from neuroast.neural.prompts import (
    JUDGE_USER_PROMPT,
    TRANSLATION_SYSTEM_PROMPT,
    TRANSLATION_USER_PROMPT,
)
from neuroast.symbolic.extractor import StructuralExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Quiet the per-file "parse tree contains errors" warnings; this script counts
# them instead of logging one line per malformed translation.
logging.getLogger("neuroast.symbolic.extractor").setLevel(logging.ERROR)

BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_DIR = Path("benchmarks/results")
OUTPUT_FILE = Path("results/resubmission/reproducibility_details.json")

# Model directory name -> how the model was actually served.
# Sourced from ``scripts/translate_benchmarks.py`` (litellm model strings) and
# the corresponding ``benchmarks/results/<dir>`` directories.
MODEL_REGISTRY = [
    {
        "result_dir": "groq_llama-3.1-8b-instant",
        "litellm_id": "groq/llama-3.1-8b-instant",
        "provider": "Groq Cloud API",
        "family": "Llama 3.1 8B Instruct",
    },
    {
        "result_dir": "groq_llama-3.3-70b-versatile",
        "litellm_id": "groq/llama-3.3-70b-versatile",
        "provider": "Groq Cloud API",
        "family": "Llama 3.3 70B Versatile",
    },
    {
        "result_dir": "ollama_llama3.1_8b",
        "litellm_id": "ollama/llama3.1:8b",
        "provider": "Ollama (local / Colab via tunnel)",
        "family": "Llama 3.1 8B Instruct",
    },
    {
        "result_dir": "ollama_qwen2.5-coder_7b",
        "litellm_id": "ollama/qwen2.5-coder:7b",
        "provider": "Ollama (local / Colab via tunnel)",
        "family": "Qwen2.5-Coder 7B",
    },
]

TRANSLATION_DECODING = {
    # ``scripts/translate_benchmarks.py`` constructs the translator with an
    # explicit temperature, overriding the library default of 0.2.
    "temperature": 0.1,
    "max_tokens": 4096,
    "top_p": None,
    "n": 1,
    "temperature_source": "scripts/translate_benchmarks.py (Translator(model, temperature=0.1))",
    "max_tokens_source": "neuroast.neural.translator.Translator default (4096)",
}

JUDGE_DECODING = {
    "temperature": None,
    "temperature_note": "provider default (no temperature passed by any judge script)",
    "timeout_seconds": {"self_judge": 60, "independent_judge": 120},
    "response_format": None,
    "response_format_note": (
        "No response_format/JSON mode: it is unsupported by the Ollama judge and "
        "is therefore omitted for both conditions to keep the prompt and call "
        "protocol matched. Responses are parsed with a tolerant JSON extractor."
    ),
}

# Five hallucination categories audited in the paper.
CATEGORY_DEFINITIONS = {
    "invented": "Control-flow constructs present in the translation with no counterpart in the source.",
    "missing": "Control-flow constructs present in the source that are absent from the translation.",
    "depth_mismatch": "Constructs that exist in both programs but at different nesting depths.",
    "lost_control_dep": "Control dependencies (condition-to-body relationships) not preserved across the translation.",
    "invalid_type_transform": "Types or type-bearing operations translated in a way that changes the value domain.",
}


def _version(package: str) -> str | None:
    """Best-effort installed-version lookup."""
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def environment_facts() -> dict:
    """Record library versions and the repository commit for provenance."""
    commit = None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Could not determine git commit hash")

    return {
        "git_commit": commit,
        "python_interpreter": sys.version.split()[0],
        "versions": {
            package: _version(package)
            for package in (
                "litellm",
                "tree-sitter",
                "tree-sitter-c",
                "tree-sitter-java",
                "networkx",
            )
        },
    }


def measure_parse_failures(model_dirs: list[str]) -> dict[str, dict]:
    """Count tree-sitter parse failures for every stored translation.

    Uses the *same* ``StructuralExtractor`` parsers as the verification
    pipeline, so the numbers describe exactly what the pipeline had to work
    with.
    """
    java_extractor = StructuralExtractor("java")
    c_extractor = StructuralExtractor("c")

    results: dict[str, dict] = {}

    for model_dir in model_dirs:
        directory = TRANSLATIONS_DIR / model_dir
        if not directory.exists():
            logger.warning("Skipping %s -- directory not found", model_dir)
            continue

        java_files = sorted(directory.glob("*.java"))
        java_failures = 0
        c_failures = 0
        pairs = 0

        for java_path in java_files:
            java_tree = java_extractor._parser.parse(java_path.read_bytes())
            if java_tree.root_node.has_error:
                java_failures += 1

            c_path = BENCHMARKS_DIR / f"{java_path.stem}.c"
            if not c_path.exists():
                continue
            pairs += 1
            c_tree = c_extractor._parser.parse(c_path.read_bytes())
            if c_tree.root_node.has_error:
                c_failures += 1

        results[model_dir] = {
            "translations": len(java_files),
            "paired_with_source": pairs,
            "java_parse_failures": java_failures,
            "java_parse_failure_rate": (
                round(java_failures / len(java_files), 4) if java_files else 0.0
            ),
            "c_parse_failures": c_failures,
        }
        logger.info(
            "[%s] %d/%d translations fail to parse cleanly",
            model_dir,
            java_failures,
            len(java_files),
        )

    return results


def pipeline_attempt_stats(model_dirs: list[str]) -> dict[str, dict]:
    """Summarise re-verification attempts and outcomes from stored results."""
    stats: dict[str, dict] = {}

    for model_dir in model_dirs:
        path = Path(f"results/progressive_{model_dir}.json")
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        summary = data.get("summary", {})
        records = data.get("records", [])
        stats[model_dir] = {
            "total_programs": summary.get("total_programs"),
            "flagged_after_tolerance": summary.get("total_hallucinations"),
            "successful_translations": summary.get("successful_translations"),
            "success_rate": summary.get("success_rate"),
            "avg_attempts": summary.get("avg_attempts"),
            "records_reaching_repair": sum(
                1 for r in records if (r.get("attempts") or 1) > 1
            ),
            "avg_verification_ms": summary.get("avg_time_ms"),
        }

    return stats


def build_fact_sheet() -> dict:
    """Assemble the full reproducibility fact sheet."""
    model_dirs = [entry["result_dir"] for entry in MODEL_REGISTRY]

    return {
        "experiment": "reproducibility_details",
        "translation_direction": "C -> Java",
        "language_pair": ["c", "java"],
        "corpus": {
            "source": "IBM Project CodeNet",
            "c_programs_available": len(list(BENCHMARKS_DIR.glob("*.c"))),
            "sampling": (
                "Programs were drawn from the CodeNet C corpus of compilable "
                "solutions. Every model translated the same deterministic file "
                "list (sorted by file name), 200 programs per model; the "
                "per-file identifiers are the file names stored under "
                "benchmarks/results/<model>/ and are listed in the repository."
            ),
            "translations_per_model": 200,
        },
        "models": MODEL_REGISTRY,
        "translation_prompts": {
            "system_prompt": TRANSLATION_SYSTEM_PROMPT,
            "user_prompt_template": TRANSLATION_USER_PROMPT,
            "source": "neuroast.neural.prompts",
        },
        "translation_decoding": TRANSLATION_DECODING,
        "judge_protocol": {
            "prompt": JUDGE_USER_PROMPT,
            "source": "neuroast.neural.prompts.JUDGE_USER_PROMPT",
            "decoding": JUDGE_DECODING,
            "self_judge_model": "ollama/llama3.1:8b (the translator itself)",
            "independent_judge_models": [
                "gemini/gemini-2.5-flash",
                "groq/llama-3.3-70b-versatile",
            ],
        },
        "hallucination_categories": CATEGORY_DEFINITIONS,
        "parsing": {
            "parser": "tree-sitter (tree_sitter_c, tree_sitter_java)",
            "failure_definition": "root_node.has_error on the parse tree",
            "per_model": measure_parse_failures(model_dirs),
        },
        "pipeline_attempts": pipeline_attempt_stats(model_dirs),
        "environment": environment_facts(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the reproducibility fact sheet as JSON."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help=f"Output JSON path (default: {OUTPUT_FILE}).",
    )
    args = parser.parse_args()

    fact_sheet = build_fact_sheet()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fact_sheet, indent=2))
    logger.info("Reproducibility fact sheet written to %s", args.output)

    print("\n% ── Reproducibility summary ──")
    print(
        f"Corpus: {fact_sheet['corpus']['c_programs_available']} C programs, "
        f"{fact_sheet['corpus']['translations_per_model']} translated per model"
    )
    print(
        f"Translation decoding: temperature={TRANSLATION_DECODING['temperature']}, "
        f"max_tokens={TRANSLATION_DECODING['max_tokens']}"
    )
    for model_dir, row in fact_sheet["parsing"]["per_model"].items():
        print(
            f"  {model_dir:32s} java parse failures: "
            f"{row['java_parse_failures']}/{row['translations']} "
            f"({row['java_parse_failure_rate'] * 100:.1f}%)"
        )


if __name__ == "__main__":
    main()
