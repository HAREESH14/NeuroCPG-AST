# NeuroAST: Architecture & Novelty

This document serves to align the AI agent and the researcher on the exact academic contribution and system architecture for the ICSE/ASE/FSE submission.

## 1. The Novelty (Academic Contribution)

**The Problem:** Existing Neuro-Symbolic code translation papers (like *AlphaTrans* or *CoTran*) rely on heavy, whole-program analysis, compiler feedback, or symbolic execution. These are slow, language-specific, and overkill for catching standard LLM "silent hallucinations" (like dropping a loop or hallucinating a branch).

**The NeuroAST Novelty:** 
> "NeuroAST introduces a **progressive, two-phase structural verification pipeline** for LLM-based legacy migration (C→Java). Instead of relying on expensive compiler feedback, NeuroAST uses a lightweight `tree-sitter` structural matcher (Phase 1) and a semantic `Joern CPG` matcher (Phase 2) as deterministic mathematical referees. This allows for fine-grained, interpretable hallucination taxonomy reporting and targeted localized repair loops, achieving high structural fidelity with minimal overhead."

## 2. System Architecture Diagram

This is the exact pipeline the agent is building in `src/neuroast/`:

```mermaid
graph TD
    %% Inputs
    C[Source C Code] --> LLM[LLM Translator \n e.g. Llama-3 / GPT-4o]
    C --> TS1[Tree-sitter C Extractor]
    
    %% Translation
    LLM -->|Translates| Java[Generated Java Code]
    Java --> TS2[Tree-sitter Java Extractor]
    
    %% Phase 1 Verification
    TS1 -->|Extracts| CFG_C[C Structural Fingerprint \n loops, branches, calls]
    TS2 -->|Extracts| CFG_Java[Java Structural Fingerprint \n loops, branches, calls]
    
    CFG_C --> V1{TreeSitter Verifier \n Phase 1}
    CFG_Java --> V1
    
    %% Phase 2 Verification (Future)
    C -.-> J1[Joern CPG Generator]
    Java -.-> J2[Joern CPG Generator]
    J1 -.-> V2{Joern CPG Verifier \n Phase 2}
    J2 -.-> V2
    
    %% Outcomes
    V1 -->|Mismatch Detected| HR[Hallucination Report]
    V2 -.->|Semantic Mismatch| HR
    
    HR -->|Targeted Repair Prompt| LLM
    V1 -->|Match Perfect| Pass[Verified Translation]
    V2 -.->|Match Perfect| Pass
    
    classDef strong fill:#d4edda,stroke:#28a745,stroke-width:2px;
    classDef light fill:#fff3cd,stroke:#ffc107,stroke-width:2px;
    classDef neural fill:#cce5ff,stroke:#007bff,stroke-width:2px;
    
    class V1 light;
    class V2 strong;
    class LLM neural;
```

## 3. How the Agent is Proceeding

The agent is **not** building a standard web app or basic script. The agent is building a **research framework**. 
1. `src/neuroast/verification/structures.py` defines the mathematical representation of `CFG_C` and `CFG_Java`.
2. `src/neuroast/verification/base.py` defines the abstract base class for `V1` and `V2` so they can be easily swapped for ablation studies.
3. The LLM integration (`litellm`) will only be used to generate the translation and apply the repair loop.
