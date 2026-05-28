# NeuroAST Project Instructions

## Project Identity
NeuroAST is a Neuro-Symbolic Code Translation Verifier aimed at top-tier academic conferences (ICSE/ASE/FSE). It measures and mitigates structural and semantic hallucinations in LLM-based cross-language code translation (C to Java). The core novelty is "Direction Inversion": using deterministic program analysis (AST + CPG) as a strict mathematical referee to grade LLM output.

## Core Directives for Agents
- **Context First**: Always consult `agent_docs/activeContext.md` and `agent_docs/systemPatterns.md` before making architectural changes. Update them when milestones are reached.
- **Current Project State (May 2026)**:
  - **Dataset**: 1,105 cleaned, compilable C source files.
  - **Translations & Evaluation**: Completed 4-way ablation experiments across 3 models (`groq_llama-3.3-70b-versatile`, `ollama_llama3.1_8b`, `ollama_qwen2.5-coder_7b`).
  - **Key Finding**: Progressive Verification (Phase 1 -> Phase 2) is ~500-2700x faster than full semantic verification while catching the majority of critical hallucinations.
- **Research Grade**: Write clean, modular, research-grade code with excellent ablation support. Prioritize clarity, reproducibility, and extensibility.
- **Paper Writing Warning**: Several sections in `Paper/Sections/` (Evaluation, Results, Discussion, Conclusion) are currently STALE and reference old data (N=49). They must be rewritten with the new multi-model data.

## Technical Standards
- **Python Version**: >= 3.11
- **Typing**: Strict type hinting is mandatory everywhere. Use `mypy` or `pyright` for validation.
- **Data Models**: Use `Pydantic v2` for all data models and serialization.
- **Verification Engine**: 
  - Phase 1: `tree-sitter` (Lightweight structural matching)
  - Phase 2: `Joern` CPG (Advanced semantic matching)
- **LLM Integration**: Use `litellm` for API routing; Ollama for local inference.

## Development Workflow
1. **Testing**: Test-driven development is required. Run `make test` frequently.
2. **Formatting**: Code must adhere to strict formatting. Run `make lint` and `make format` (using `ruff` if available).
3. **Task Automation**: Use the provided `Makefile` for standardized commands.

## Knowledge Graph (Graphify)
- **Check the Graph**: This project uses `graphify` to maintain a structural and semantic map. Always check `graphify-out/graph.json` when answering complex questions about codebase architecture or cross-file dependencies.
- **Updating**: Code AST is automatically extracted on `git commit` via hooks. For semantic updates (e.g., when adding new docs or papers), run `graphify --update` to sync the LLM knowledge graph.
