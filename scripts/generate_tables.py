"""
Generate camera-ready paper tables from NeuroAST experiment results.

Reads all result JSONs from results/ and generates:
  - Table 1: Ablation results (per-model, per-mode)
  - Table 2: Cross-model hallucination taxonomy distribution
  - Table 3: Per-phase timing comparison

Outputs: results/paper_tables.md (Markdown) + Paper/tables/*.tex (LaTeX)

Usage:
    python scripts/generate_tables.py
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_results(results_dir: Path) -> dict[str, dict]:
    """Load all result JSONs, keyed by 'mode_model'."""
    results = {}
    for f in sorted(results_dir.glob("*.json")):
        if f.name == "paper_tables.json":
            continue
        data = json.loads(f.read_text())
        results[f.stem] = data
    return results


def extract_model_mode(filename: str) -> tuple[str, str]:
    """Parse 'progressive_groq_llama-3.3-70b-versatile' → (mode, model)."""
    modes = ["none", "structural_only", "semantic_only", "progressive"]
    for mode in modes:
        if filename.startswith(mode + "_"):
            model = filename[len(mode) + 1:]
            return mode, model
        elif filename == mode:
            return mode, "default"
    return "unknown", filename


def generate_table1_ablation(results: dict) -> str:
    """Table 1: Ablation Results per model.
    
    | Model | Mode | Files | Hallucinations | Avg Confidence | Avg Time (ms) |
    """
    lines = [
        "## Table 1: Verification Ablation Results (Multi-Model)",
        "",
        "| Model | Configuration | Files | Hallucinations Detected | Avg Confidence | Avg Time (ms) |",
        "|:------|:-------------|------:|------------------------:|---------------:|--------------:|",
    ]

    # Group by model
    model_data: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for key, data in results.items():
        mode, model = extract_model_mode(key)
        model_data[model].append((mode, data.get("summary", {})))

    mode_order = ["none", "structural_only", "semantic_only", "progressive"]
    mode_labels = {
        "none": "None (Baseline)",
        "structural_only": "Structural (Phase 1)",
        "semantic_only": "Semantic (Phase 2)",
        "progressive": "Progressive",
    }

    for model in sorted(model_data.keys()):
        entries = {mode: summary for mode, summary in model_data[model]}
        for mode in mode_order:
            if mode not in entries:
                continue
            s = entries[mode]
            lines.append(
                f"| {model} | {mode_labels.get(mode, mode)} "
                f"| {s.get('total_programs', 0)} "
                f"| {s.get('total_hallucinations', 0)} "
                f"| {s.get('avg_confidence', 0):.3f} "
                f"| {s.get('avg_time_ms', 0):.1f} |"
            )
        lines.append("|---|---|---|---|---|---|")  # Visual separator

    return "\n".join(lines)


def generate_table2_taxonomy(results: dict) -> str:
    """Table 2: Hallucination taxonomy distribution across models."""
    lines = [
        "## Table 2: Cross-Model Hallucination Taxonomy Distribution",
        "",
    ]

    # Collect progressive results per model
    models: dict[str, dict] = {}
    for key, data in results.items():
        mode, model = extract_model_mode(key)
        if mode == "progressive":
            cats = data.get("summary", {}).get("hallucinations_by_category", {})
            total = data.get("summary", {}).get("total_hallucinations", 0)
            models[model] = {"categories": cats, "total": total}

    if not models:
        return "## Table 2: No progressive results found.\n"

    # Collect all categories
    all_cats: set[str] = set()
    for m in models.values():
        all_cats.update(m["categories"].keys())

    cat_order = [
        "missing", "invented", "depth_mismatch", "reordered",
        "broken_def_use", "lost_control_dep", "invalid_type_transform",
        "data_flow_invention",
    ]
    sorted_cats = [c for c in cat_order if c in all_cats]
    sorted_cats += sorted(all_cats - set(cat_order))

    # Header
    model_names = sorted(models.keys())
    header = "| Category |" + " | ".join(f" {m} " for m in model_names) + " |"
    separator = "|:---------|" + " | ".join("------:" for _ in model_names) + " |"
    lines.extend([header, separator])

    for cat in sorted_cats:
        row = f"| {cat} |"
        for model in model_names:
            count = models[model]["categories"].get(cat, 0)
            total = models[model]["total"]
            pct = (count / total * 100) if total > 0 else 0
            row += f" {count} ({pct:.1f}%) |"
        lines.append(row)

    # Totals row
    row = "| **Total** |"
    for model in model_names:
        row += f" **{models[model]['total']}** |"
    lines.append(row)

    return "\n".join(lines)


def generate_table3_timing(results: dict) -> str:
    """Table 3: Per-model timing comparison."""
    lines = [
        "## Table 3: Verification Overhead (Wall-Clock Time)",
        "",
        "| Model | Phase 1 Avg (ms) | Progressive Avg (ms) | Speedup vs Full |",
        "|:------|----------------:|-----------:|----------:|",
    ]

    model_timing: dict[str, dict[str, float]] = defaultdict(dict)
    for key, data in results.items():
        mode, model = extract_model_mode(key)
        avg_time = data.get("summary", {}).get("avg_time_ms", 0)
        model_timing[model][mode] = avg_time

    for model in sorted(model_timing.keys()):
        p1 = model_timing[model].get("structural_only", 0)
        prog = model_timing[model].get("progressive", 0)
        sem = model_timing[model].get("semantic_only", 0)
        speedup = f"{sem / prog:.1f}x" if prog > 0 and sem > 0 else "N/A"
        lines.append(f"| {model} | {p1:.1f} | {prog:.1f} | {speedup} |")

    return "\n".join(lines)


def main() -> None:
    results_dir = Path("results")
    results = load_results(results_dir)

    if not results:
        logger.error("No result JSONs found in %s/", results_dir)
        return

    logger.info("Loaded %d result files", len(results))

    # Generate tables
    table1 = generate_table1_ablation(results)
    table2 = generate_table2_taxonomy(results)
    table3 = generate_table3_timing(results)

    # Combine into paper_tables.md
    output = "\n\n".join([table1, table2, table3])
    output += "\n\n*Generated automatically by `scripts/generate_tables.py`*\n"

    out_path = results_dir / "paper_tables.md"
    out_path.write_text(output)
    logger.info("✅ Written %s", out_path)

    # Also save raw data as JSON for programmatic access
    json_path = results_dir / "paper_tables.json"
    json_path.write_text(json.dumps({
        "table1_models": list(results.keys()),
        "generated_from": [str(f) for f in results_dir.glob("*.json") if f.name != "paper_tables.json"],
    }, indent=2))

    logger.info("🎉 Tables generated!")


if __name__ == "__main__":
    main()
