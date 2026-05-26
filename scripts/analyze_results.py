import json
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_ablation_table(results_dir: Path, output_file: Path):
    """Generates the 4-way ablation experiment table."""
    modes = ["none", "structural_only", "semantic_only", "progressive"]
    data = []
    
    for mode in modes:
        path = results_dir / f"{mode}.json"
        if not path.exists():
            continue
            
        with path.open() as f:
            j = json.load(f)
            summary = j["summary"]
            
        data.append({
            "Configuration": mode.replace("_", " ").title().replace("Only", "(Phase)"),
            "Total Files": summary["total_programs"],
            "Avg Confidence": f"{summary['avg_confidence']:.2f}",
            "Hallucinations Detected": summary["total_hallucinations"],
        })
        
    df = pd.DataFrame(data)
    markdown_table = df.to_markdown(index=False)
    
    with output_file.open("w") as f:
        f.write("## Table 1: Verification Ablation Results\n\n")
        f.write(markdown_table)
        f.write("\n\n")
        
    logger.info("Generated Table 1: Ablation Results")

def generate_taxonomy_table(results_dir: Path, output_file: Path):
    """Generates the Hallucination Taxonomy distribution table using Progressive results."""
    progressive_path = results_dir / "progressive.json"
    if not progressive_path.exists():
        logger.error("progressive.json not found for taxonomy analysis.")
        return
        
    with progressive_path.open() as f:
        j = json.load(f)
        
    cats = j["summary"]["hallucinations_by_category"]
    
    # Sort by frequency
    sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    
    data = []
    total = sum(cats.values())
    
    for cat, count in sorted_cats:
        percentage = (count / total) * 100 if total > 0 else 0
        data.append({
            "Hallucination Category": cat,
            "Count": count,
            "% of Total": f"{percentage:.1f}%"
        })
        
    df = pd.DataFrame(data)
    markdown_table = df.to_markdown(index=False)
    
    with output_file.open("a") as f:
        f.write("## Table 2: Structural & Semantic Hallucination Distribution\n\n")
        f.write(markdown_table)
        f.write("\n\n")
        f.write(f"*Total Hallucinations Detected: {total}*\n")
        
    logger.info("Generated Table 2: Taxonomy Distribution")

def main():
    results_dir = Path("results")
    if not results_dir.exists():
        logger.error("Results directory not found.")
        return
        
    output_file = results_dir / "paper_tables.md"
    generate_ablation_table(results_dir, output_file)
    generate_taxonomy_table(results_dir, output_file)
    logger.info(f"All tables exported to {output_file}")

if __name__ == "__main__":
    main()
