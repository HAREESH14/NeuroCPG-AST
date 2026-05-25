# Product Context

## Why this project exists
NeuroAST is a neuro-symbolic framework designed for measuring and mitigating structural hallucinations in LLM-based cross-language code translation (specifically C to Java). 
Previous purely rule-based translator approaches were rejected by top academic venues (ICSE/ASE/FSE) for being "yet another translator". 
NeuroAST pivots to a verification + hallucination measurement instrument. It treats an LLM as the translator and uses a deterministic structural engine (Tree-sitter and Joern CPG) as a referee to catch hallucinations and prompt localized repairs.

## Problems it solves
1. Silent hallucinations in LLM-generated code translations (e.g., dropped loops, invented branches).
2. The lack of lightweight, interpretable verification for translation fidelity.
3. Provides a clean empirical ablation study framework for research (LLM vs Tree-sitter StructuralMatcher vs Joern CPG Matcher).

## Core Value
Providing a progressive, fast, two-phase verification strategy (Phase 1: Lightweight tree-sitter, Phase 2: Advanced CPG semantic grounding) that leads to highly reliable cross-language legacy migration.
