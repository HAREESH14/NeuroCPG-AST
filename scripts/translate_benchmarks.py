import asyncio
import logging
from pathlib import Path

from neuroast.neural.translator import Translator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def translate_all():
    benchmarks_dir = Path("benchmarks/datasets")
    results_dir = Path("benchmarks/results")
    
    models = ["groq/llama-3.3-70b-versatile"]
    
    translator = Translator(model=models[0], temperature=0.1)
    
    c_files = list(benchmarks_dir.glob("*.c"))[:200]
    logger.info(f"Found {len(c_files)} C files to translate.")
    
    for model in models:
        model_name_safe = model.replace("/", "_")
        model_out_dir = results_dir / model_name_safe
        model_out_dir.mkdir(parents=True, exist_ok=True)
        
        for c_file in c_files:
            java_out_path = model_out_dir / f"{c_file.stem}.java"
            if java_out_path.exists():
                logger.info(f"Skipping {c_file.name}, already translated.")
                continue
                
            logger.info(f"Translating {c_file.name} with {model}...")
            c_code = c_file.read_text()
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    java_code = await translator.translate(c_code)
                    java_out_path.write_text(java_code)
                    logger.info(f"Saved {java_out_path}")
                    break
                except Exception as e:
                    logger.error(f"Failed to translate {c_file.name} (attempt {attempt+1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        logger.info("Sleeping 10s to avoid rate limit...")
                        await asyncio.sleep(10)
            
            # Sleep between requests to pace them out and respect TPM
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(translate_all())
