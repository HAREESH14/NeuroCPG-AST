import sys
import logging
from pathlib import Path
from neuroast.symbolic.cpg_extractor import CPGExtractor
from neuroast.symbolic.normalizer import CPGNormalizer
from neuroast.verification.semantic_matcher import SemanticMatcher
from neuroast.verification.structures import SemanticAlignmentReport

logging.basicConfig(level=logging.INFO)

def main():
    extractor = CPGExtractor()
    normalizer_c = CPGNormalizer("c")
    normalizer_java = CPGNormalizer("java")
    matcher = SemanticMatcher()

    c_file = Path("benchmarks/datasets/binary_search.c")
    java_file = Path("/tmp/binary_search_correct.java")
    java_hallu_file = Path("/tmp/binary_search_hallucinated.java")

    print(f"Extracting CPG for {c_file}...")
    c_cpg = extractor.extract_from_file(c_file, "c")
    c_norm = normalizer_c.normalize(c_cpg)
    
    print(f"Extracting CPG for {java_file}...")
    java_cpg = extractor.extract_from_file(java_file, "java")
    java_norm = normalizer_java.normalize(java_cpg)

    print(f"Extracting CPG for {java_hallu_file}...")
    java_hallu_cpg = extractor.extract_from_file(java_hallu_file, "java")
    java_hallu_norm = normalizer_java.normalize(java_hallu_cpg)

    print("\n--- Semantic Matching: Correct ---")
    report_correct = matcher.match(c_norm, java_norm)
    print(f"Aligned: {report_correct.is_aligned}, Confidence: {report_correct.confidence}")
    for h in report_correct.hallucinations:
        print(f" - {h}")

    print("\n--- Semantic Matching: Hallucinated ---")
    report_hallu = matcher.match(c_norm, java_hallu_norm)
    print(f"Aligned: {report_hallu.is_aligned}, Confidence: {report_hallu.confidence}")
    for h in report_hallu.hallucinations:
        print(f" - {h}")

if __name__ == "__main__":
    main()
