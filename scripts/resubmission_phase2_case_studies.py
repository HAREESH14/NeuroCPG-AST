"""
Extract Phase 2 Semantic Detection Case Studies.

Addresses Reviewer R2.3:
  - Extracts ALL 11 real-world semantic detections from progressive results
  - For each detection, shows:
    * The C source construct
    * The Java translation
    * The hallucination category (lost_control_dep / invalid_type_transform)
    * The file context
  - Outputs both a structured JSON and a human-readable Markdown
    suitable for inclusion in the paper as a case-study subsection

Usage:
    uv run python scripts/resubmission_phase2_case_studies.py
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
RESULTS_DIR = Path("results")
BENCHMARKS_DIR = Path("benchmarks/datasets")
TRANSLATIONS_BASE = Path("benchmarks/results")
OUTPUT_DIR = Path("results/resubmission")

SEMANTIC_CATEGORIES = {"lost_control_dep", "invalid_type_transform", "data_flow_invention"}


@dataclass
class SemanticCaseStudy:
    """A single Phase 2 semantic detection for case study presentation."""

    case_id: int
    model: str
    source_file: str
    category: str
    count: int
    total_hallucinations_in_file: int
    structural_hallucinations: int
    semantic_hallucinations: int
    confidence: float
    c_source: str = ""
    java_translation: str = ""
    adjudication: str = ""  # To be filled: TP (true positive) / FP / BORDERLINE


def extract_semantic_detections() -> list[SemanticCaseStudy]:
    """
    Extract all files with Phase 2 semantic detections from progressive results.
    """
    cases: list[SemanticCaseStudy] = []
    case_id = 0

    for json_file in sorted(RESULTS_DIR.glob("progressive_*.json")):
        data = json.loads(json_file.read_text())
        model_name = json_file.stem.replace("progressive_", "")
        model_dir = TRANSLATIONS_BASE / model_name

        for record in data.get("records", []):
            semantic_count = record.get("semantic_hallucinations", 0)
            if semantic_count == 0:
                continue

            source_file = record["source_file"]
            categories = record.get("hallucination_categories", {})

            # Identify which semantic categories were detected
            for cat, count in categories.items():
                if cat not in SEMANTIC_CATEGORIES or count == 0:
                    continue

                case_id += 1
                c_path = BENCHMARKS_DIR / source_file
                java_path = model_dir / f"{Path(source_file).stem}.java"

                c_source = c_path.read_text(errors="replace") if c_path.exists() else "[NOT FOUND]"
                java_trans = java_path.read_text(errors="replace") if java_path.exists() else "[NOT FOUND]"

                cases.append(SemanticCaseStudy(
                    case_id=case_id,
                    model=model_name,
                    source_file=source_file,
                    category=cat,
                    count=count,
                    total_hallucinations_in_file=record.get("total_hallucinations", 0),
                    structural_hallucinations=record.get("structural_hallucinations", 0),
                    semantic_hallucinations=semantic_count,
                    confidence=record.get("final_confidence", 0.0),
                    c_source=c_source,
                    java_translation=java_trans,
                ))

    return cases


def _truncate_code(code: str, max_lines: int = 80) -> str:
    """Truncate code for display."""
    lines = code.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n\n// ... [{len(lines) - max_lines} more lines]"
    return code


def export_case_studies(
    cases: list[SemanticCaseStudy],
    json_path: Path,
    md_path: Path,
) -> None:
    """Export case studies as JSON and Markdown."""
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # ── JSON export ──────────────────────────────────────────────────
    json_report = {
        "experiment": "phase2_case_studies",
        "total_semantic_detections": len(cases),
        "by_category": {},
        "by_model": {},
        "cases": [],
    }

    for case in cases:
        json_report["cases"].append({
            "case_id": case.case_id,
            "model": case.model,
            "source_file": case.source_file,
            "category": case.category,
            "count": case.count,
            "total_hallucinations_in_file": case.total_hallucinations_in_file,
            "structural_hallucinations": case.structural_hallucinations,
            "semantic_hallucinations": case.semantic_hallucinations,
            "confidence": case.confidence,
            "adjudication": case.adjudication,
            "c_source_lines": len(case.c_source.splitlines()),
            "java_translation_lines": len(case.java_translation.splitlines()),
        })

        # Aggregate counts
        cat = case.category
        json_report["by_category"][cat] = json_report["by_category"].get(cat, 0) + case.count
        json_report["by_model"][case.model] = json_report["by_model"].get(case.model, 0) + case.count

    json_path.write_text(json.dumps(json_report, indent=2))
    logger.info("Exported JSON to %s", json_path)

    # ── Markdown export ──────────────────────────────────────────────
    md_lines: list[str] = []
    md_lines.append("# Phase 2 Semantic Detection Case Studies\n")
    md_lines.append(f"**Total semantic detections across all models: {len(cases)}**\n")
    md_lines.append("## Summary\n")
    md_lines.append("| Category | Count |")
    md_lines.append("|----------|------:|")
    for cat, count in sorted(json_report["by_category"].items()):
        md_lines.append(f"| {cat} | {count} |")
    md_lines.append("")
    md_lines.append("| Model | Semantic Detections |")
    md_lines.append("|-------|--------------------:|")
    for model, count in sorted(json_report["by_model"].items()):
        md_lines.append(f"| {model} | {count} |")
    md_lines.append("")

    # Individual case studies
    md_lines.append("---\n")
    md_lines.append("## Individual Case Studies\n")

    for case in cases:
        md_lines.append(f"### Case {case.case_id}: {case.source_file} ({case.model})\n")
        md_lines.append(f"- **Category**: `{case.category}` (×{case.count})")
        md_lines.append(f"- **File totals**: {case.total_hallucinations_in_file} total "
                       f"({case.structural_hallucinations} structural, "
                       f"{case.semantic_hallucinations} semantic)")
        md_lines.append(f"- **Confidence**: {case.confidence:.4f}")
        md_lines.append(f"- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`\n")

        md_lines.append("<details>")
        md_lines.append(f"<summary>C Source ({len(case.c_source.splitlines())} lines)</summary>\n")
        md_lines.append("```c")
        md_lines.append(_truncate_code(case.c_source))
        md_lines.append("```")
        md_lines.append("</details>\n")

        md_lines.append("<details>")
        md_lines.append(f"<summary>Java Translation ({len(case.java_translation.splitlines())} lines)</summary>\n")
        md_lines.append("```java")
        md_lines.append(_truncate_code(case.java_translation))
        md_lines.append("```")
        md_lines.append("</details>\n")

        md_lines.append("**Analysis**: _[Describe the specific broken dependency edge or "
                       "type transformation that Phase 2 detected. Explain why this would "
                       "be invisible to structural analysis.]_\n")
        md_lines.append("---\n")

    md_path.write_text("\n".join(md_lines))
    logger.info("Exported Markdown case studies to %s", md_path)

    # ── Also check semantic-only results for additional context ───────
    print("\n── Additional Context: Semantic-Only vs Progressive ──")
    for json_file in sorted(RESULTS_DIR.glob("semantic_only_*.json")):
        data = json.loads(json_file.read_text())
        model_name = json_file.stem.replace("semantic_only_", "")
        summary = data.get("summary", {})
        cats = summary.get("hallucinations_by_category", {})
        semantic_cats = {k: v for k, v in cats.items() if k in SEMANTIC_CATEGORIES}
        print(f"  {model_name} (semantic-only): {summary.get('total_hallucinations', 0)} total, "
              f"semantic={semantic_cats}")

    print("\n── Note ──")
    print("The progressive pipeline finds FEWER semantic detections than semantic-only")
    print("because it only runs Phase 2 on files that pass Phase 1 (structurally clean).")
    print("Files with structural issues are already caught by Phase 1 and don't reach Phase 2.")


def main() -> None:
    logger.info("Extracting Phase 2 semantic case studies...")

    cases = extract_semantic_detections()
    logger.info("Found %d semantic detection cases across all models", len(cases))

    # Print summary
    by_cat: dict[str, int] = {}
    by_model: dict[str, int] = {}
    for case in cases:
        by_cat[case.category] = by_cat.get(case.category, 0) + case.count
        by_model[case.model] = by_model.get(case.model, 0) + case.count

    logger.info("By category: %s", by_cat)
    logger.info("By model: %s", by_model)

    # Export
    export_case_studies(
        cases,
        json_path=OUTPUT_DIR / "phase2_case_studies.json",
        md_path=OUTPUT_DIR / "phase2_case_studies.md",
    )

    logger.info("✅ Phase 2 case studies extracted!")
    logger.info("Next: Review %s and fill in the adjudication + analysis for each case",
                OUTPUT_DIR / "phase2_case_studies.md")


if __name__ == "__main__":
    main()
