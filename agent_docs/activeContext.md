# Active Context

## Current Status
We are in the initial setup phase of the NeuroAST project. The repository structure has just been upgraded to a professional layout. The project is being framed for submission to top-tier conferences (ICSE/ASE/FSE 2027) by pivoting away from a simple "rule-based translator with LLM fallback" to a "Progressive Neuro-Symbolic Code Translation Verifier".

## Next Immediate Steps
1. Scaffold the core directory structure in `src/neuroast` (core, neural, symbolic, verification, utils).
2. Implement `verification/structures.py` (Pydantic models for AST extraction).
3. Implement `verification/base.py` (Abstract Verifier class).
4. Build the Phase 1 Tree-sitter extractor (`TreeSitterVerifier`).
5. Develop the hallucination taxonomy reporting capabilities.

## Recent Changes
- Created `agent_docs/` Memory Bank to maintain AI agent context natively.
- Initialized standard `pyproject.toml` with `tree-sitter`, `joern`, `litellm`, `pydantic`, and `networkx` dependencies.
- Migrated legacy chat history to `.agents/chat_history`.
