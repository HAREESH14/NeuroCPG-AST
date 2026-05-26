import logging
from pathlib import Path

from neuroast.utils.metrics import MetricsCollector
from neuroast.verification.progressive_verifier import ProgressiveVerifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_experiment(mode: str, model_dir: Path, output_json: Path):
    benchmarks_dir = Path("benchmarks/datasets")
    c_files = list(benchmarks_dir.glob("*.c"))
    
    # Modes: none, structural_only, semantic_only, progressive
    if mode == "none":
        verifier = None
    else:
        verifier = ProgressiveVerifier(mode=mode)
    
    collector = MetricsCollector()
    
    for c_file in c_files:
        java_file = model_dir / f"{c_file.stem}.java"
        if not java_file.exists():
            continue
            
        c_code = c_file.read_text()
        java_code = java_file.read_text()
        
        if verifier:
            logger.info(f"[{mode}] Verifying {c_file.name}...")
            try:
                report = verifier.verify(c_code, java_code)
                collector.add_from_report(report, source_file=c_file.name, model=model_dir.name)
            except Exception as e:
                logger.error(f"Error verifying {c_file.name}: {e}")
        else:
            # Baseline: no verification, just record a perfectly aligned report
            from neuroast.verification.structures import AlignmentReport
            dummy_report = AlignmentReport(is_aligned=True, confidence=1.0, phase="structural")
            collector.add_from_report(dummy_report, source_file=c_file.name, model=model_dir.name)
            
    # Export results
    collector.export_json(output_json)
    logger.info(f"Saved results for {mode} to {output_json}")
    
def main():
    model_name = "groq_llama-3.3-70b-versatile"
    model_dir = Path("benchmarks/results") / model_name
    
    if not model_dir.exists():
        logger.error(f"No translations found in {model_dir}")
        return
        
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    modes = ["none", "structural_only", "semantic_only", "progressive"]
    for mode in modes:
        out_file = results_dir / f"{mode}.json"
        run_experiment(mode, model_dir, out_file)
        
if __name__ == "__main__":
    main()
