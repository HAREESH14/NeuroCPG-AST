# System Patterns

## Architecture
We use a Two-Phase Verification Strategy:
1. **Phase 1 (Lightweight)**: Uses `tree-sitter` for syntactic/structural matching (loops, branches, depth, calls). Fast and catches superficial hallucinations.
2. **Phase 2 (Advanced)**: Uses `Joern` (CPG) for semantic matching (data-flow, pointer-arithmetic vs object references). Highly tolerant of valid idioms but strict on functionality.

## Core Design Patterns (Agent Rules)
- **Abstract Verifier Pattern**: Core classes must inherit from an abstract `Verifier` base class to allow easy swapping (e.g., `TreeSitterVerifier` vs `JoernCPGVerifier`) for ablation studies.
- **Pydantic Models**: All data models and outputs should use `Pydantic v2` for type safety and serialization.
- **Error Handling**: Expect LLM hallucinations and parse failures. Code must robustly handle bad AST/CPG inputs.
- **Logging for Paper**: All metrics (overhead, hallucination rates, iterations) must be serialized to JSON/CSV for conference paper tables.

## Tech Stack
- Python 3.11+
- tree-sitter, tree-sitter-c, tree-sitter-java
- litellm (LLM routing)
- cpgqls-client, cpggen (Joern CPG)
- networkx (Graph matching)
- typer, rich (CLI)
- pydantic, pydantic-settings
- pytest
