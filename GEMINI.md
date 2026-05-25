# NeuroAST Project Instructions

## Project Identity
NeuroAST is a Neuro-Symbolic Code Translation Verifier aimed at top-tier academic conferences (ICSE/ASE/FSE). It measures and mitigates structural hallucinations in LLM-based cross-language code translation (C to Java).

## Core Directives for Agents
- **Context First**: Always consult `agent_docs/activeContext.md` and `agent_docs/systemPatterns.md` before making architectural changes. Update them when milestones are reached.
- **Research Grade**: Write clean, modular, research-grade code with excellent ablation support. Prioritize clarity, reproducibility, and extensibility.
- **Fail Gracefully**: Expect LLM hallucinations and parse failures. Code must robustly handle bad AST/CPG inputs.
- **Data Collection**: All metrics (overhead, hallucination rates, repair iterations) must be exportable to JSON/CSV for conference paper tables.

## Technical Standards
- **Python Version**: >= 3.11
- **Typing**: Strict type hinting is mandatory everywhere. Use `mypy` or `pyright` for validation.
- **Data Models**: Use `Pydantic v2` for all data models and serialization.
- **Verification Engine**: 
  - Phase 1: `tree-sitter` (Lightweight structural matching)
  - Phase 2: `Joern` CPG (Advanced semantic matching)
- **LLM Integration**: Use `litellm` for all LLM routing.

## Development Workflow
1. **Testing**: Test-driven development is required. Run `make test` frequently.
2. **Formatting**: Code must adhere to strict formatting. Run `make lint` and `make format` (using `ruff` if available).
3. **Task Automation**: Use the provided `Makefile` for standardized commands.

## Knowledge Graph (Graphify)
- **Check the Graph**: This project uses `graphify` to maintain a structural and semantic map. Always check `graphify-out/graph.json` when answering complex questions about codebase architecture or cross-file dependencies.
- **Updating**: Code AST is automatically extracted on `git commit` via hooks. For semantic updates (e.g., when adding new docs or papers), run `make graph` to update the LLM knowledge graph.
