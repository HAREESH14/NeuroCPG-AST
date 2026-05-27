<p align="center">
  <img src="Paper/fig/architecturediagram.png" alt="NeuroAST Architecture" width="800"/>
</p>

<h1 align="center">NeuroAST</h1>
<p align="center">
  <strong>Progressive Neuro-Symbolic Verification for Algorithmic Code Translation</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-%3E%3D3.11-blue.svg" alt="Python 3.11+"/></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"/></a>
  <a href="https://github.com/joernio/joern"><img src="https://img.shields.io/badge/Phase%202-Joern%20CPG-orange.svg" alt="Joern CPG"/></a>
  <a href="https://tree-sitter.github.io/tree-sitter/"><img src="https://img.shields.io/badge/Phase%201-tree--sitter-blueviolet.svg" alt="tree-sitter"/></a>
</p>

---

## Overview

**NeuroAST** is a progressive neuro-symbolic verifier that detects structural and semantic hallucinations in LLM-generated cross-language code translations (C → Java). Instead of feeding Code Property Graphs (CPGs) *into* LLMs to improve generation, NeuroAST uses deterministic program analysis to *verify* the LLM's output after the fact.

### Key Results

| Metric | Value |
|--------|-------|
| Corpus | 1,105 C programs from IBM Project CodeNet |
| Models evaluated | 3 (Llama-3.3-70B, Llama-3.1-8B, Qwen-2.5-Coder-7B) |
| Hallucinations detected | 477 – 1,438 per model (Progressive mode) |
| Average verification time | < 1 ms per file |
| LLM self-verification recall | 35.1% (vs. NeuroAST's deterministic detection) |
| Manual precision | 100% (n=50, 95% CI: [92.9%, 100%]) |

---

## Architecture

NeuroAST implements a **two-phase progressive pipeline**:

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│  C Source     │     │  Phase 1            │     │  Phase 2             │
│  Program      │────▶│  AST Structural     │────▶│  CPG Semantic        │
│              │     │  Matching           │     │  Matching (NormPDG)  │
└──────────────┘     │  (tree-sitter, <1ms)│     │  (Joern, ~500ms)     │
                     └─────────┬───────────┘     └──────────┬───────────┘
┌──────────────┐               │                            │
│  LLM-Generated│              │ Fast Fail                  │ Deep Verify
│  Java         │──────────────┤ (structural faults)        │ (semantic faults)
│  Translation  │              │                            │
└──────────────┘               ▼                            ▼
                     ┌─────────────────────────────────────────────┐
                     │            Tolerance Engine                  │
                     │  (idiom-equivalence rules: malloc/new,      │
                     │   for-each, GC, numeric casts)              │
                     └─────────────────────┬───────────────────────┘
                                           │
                                           ▼
                              ┌───────────────────────┐
                              │  Verification Report   │
                              │  + 11-Category         │
                              │  Hallucination Taxonomy │
                              └───────────────────────┘
```

- **Phase 1 (Structural):** Extracts control-flow skeletons from both source and target using `tree-sitter`. Catches Missing, Invented, and Depth Mismatch hallucinations in sub-millisecond time.
- **Phase 2 (Semantic):** Extracts Code Property Graphs via `Joern`, normalizes them into a cross-language NormPDG, and compares data-flow dependencies. Only invoked for files that pass Phase 1.
- **Tolerance Engine:** Suppresses false positives from valid cross-language idiom transformations (e.g., `malloc`→`new`, `for`→`for-each`, manual memory→GC). Reduces false positives by 80%.

---

## Project Structure

```
neuroast/
├── src/neuroast/               # Core library
│   ├── core/                   # Configuration and pipeline orchestration
│   │   ├── config.py           # Pydantic settings (env-based)
│   │   └── pipeline.py         # End-to-end verification pipeline
│   ├── symbolic/               # Deterministic program analysis
│   │   ├── extractor.py        # Phase 1: tree-sitter AST extraction
│   │   ├── cpg_extractor.py    # Phase 2: Joern CPG extraction
│   │   ├── normalizer.py       # NormPDG normalization layer
│   │   ├── c_queries.py        # tree-sitter queries for C
│   │   └── java_queries.py     # tree-sitter queries for Java
│   ├── verification/           # Verification engine
│   │   ├── matcher.py          # Phase 1: Structural CFG matching
│   │   ├── semantic_matcher.py # Phase 2: NormPDG semantic matching
│   │   ├── progressive_verifier.py  # Progressive pipeline (Alg. 2)
│   │   ├── tolerance.py        # Tolerance Engine (idiom rules)
│   │   ├── structures.py       # Pydantic data models
│   │   └── joern_client.py     # Joern HTTP client
│   ├── neural/                 # LLM integration
│   │   ├── translator.py       # LLM-based C→Java translation
│   │   ├── repair.py           # LLM-based repair (experimental)
│   │   └── prompts.py          # Prompt templates
│   └── cli.py                  # Typer CLI interface
│
├── scripts/                    # Experiment automation
│   ├── translate_benchmarks.py # Batch LLM translation
│   ├── run_benchmarks.py       # Four-way ablation runner
│   ├── generate_tables.py      # LaTeX table generation
│   ├── llm_judge_baseline.py   # LLM-as-a-Judge experiment
│   ├── analyze_results.py      # Result analysis utilities
│   └── sample_for_validation.py # Random sampling for manual audit
│
├── benchmarks/
│   ├── datasets/               # 1,105 C source files (CodeNet)
│   └── results/                # LLM translations (per-model dirs)
│       ├── groq_llama-3.3-70b-versatile/
│       ├── ollama_llama3.1_8b/
│       └── ollama_qwen2.5-coder_7b/
│
├── results/                    # Verification results (JSON)
│   ├── progressive_*.json      # Progressive mode results
│   ├── structural_only_*.json  # Phase 1 only results
│   ├── semantic_only_*.json    # Phase 2 only results
│   ├── llm_judge_baseline.json # LLM-as-a-Judge results
│   ├── paper_tables.json       # Generated table data
│   └── validation_sample.csv   # 50-sample manual audit
│
├── tests/                      # Test suite
│   ├── test_extractor.py       # AST extraction tests
│   ├── test_matcher.py         # Structural matching tests
│   ├── test_phase2.py          # Semantic matching tests
│   ├── test_normalizer.py      # NormPDG normalization tests
│   ├── test_structures.py      # Data model tests
│   └── test_metrics.py         # Metric computation tests
|
├── docker-compose.yml          # Joern CPG server (Phase 2)
├── pyproject.toml              # Project metadata and dependencies
├── Makefile                    # Task automation
└── .env.example                # Environment configuration template
```

---

## Prerequisites

| Dependency | Version | Purpose |
|-----------|---------|---------|
| **Python** | ≥ 3.11 | Runtime |
| **uv** | Latest | Package manager ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| **Docker** | ≥ 20.10 | Joern CPG server (Phase 2 only) |
| **Ollama** | Latest | Local LLM inference ([install](https://ollama.ai)) |

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/HAREESH14/NeuroCPG-AST.git
cd neuroast
```

### 2. Set Up the Python Environment

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (creates .venv automatically)
make setup
# or manually:
uv sync --group dev
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your API keys and model preferences
```

**Supported LLM providers:**

| Provider | Model | Configuration |
|----------|-------|--------------|
| **Groq** (cloud, free tier) | `groq/llama-3.3-70b-versatile` | Set `GROQ_API_KEY` |
| **Ollama** (local, free) | `ollama/llama3.1:8b`, `ollama/qwen2.5-coder:7b` | Start Ollama server |
| **OpenAI** (cloud, paid) | `gpt-4o` | Set `OPENAI_API_KEY` |

### 4. Start Joern (Phase 2 Only)

Phase 2 semantic verification requires the Joern CPG server. Skip this step if you only need Phase 1 structural verification.

```bash
# Start Joern in background (takes ~60-90s to become healthy)
make joern-up

# Check if Joern is ready
make joern-status

# Verify with a test query
make joern-test
```

### 5. Pull LLM Models (Ollama)

```bash
# For local inference
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
```

---

## Usage

### CLI Interface

NeuroAST provides a Typer-based CLI for all operations:

#### Verify a Single File

```bash
# Full progressive verification (Phase 1 + Phase 2)
make verify SRC=benchmarks/datasets/53_maximum_subarray.c

# Or directly:
uv run python -m neuroast.cli verify benchmarks/datasets/53_maximum_subarray.c
```

#### Extract Structural Fingerprint

```bash
# Extract control-flow skeleton from a C file
make extract SRC=benchmarks/datasets/53_maximum_subarray.c LANG=c

# Extract from a Java file
make extract SRC=path/to/File.java LANG=java
```

#### Compare Source and Target

```bash
# Compare C source against Java translation
make compare SRC=benchmarks/datasets/53_maximum_subarray.c TGT=path/to/Translation.java
```

---

## Reproducing the Experiments

The complete experimental pipeline can be reproduced in four steps:

### Step 1: Translate C Programs to Java

```bash
# Translate 200 random programs per model
uv run python scripts/translate_benchmarks.py \
  --model groq/llama-3.3-70b-versatile \
  --count 200

uv run python scripts/translate_benchmarks.py \
  --model ollama/llama3.1:8b \
  --count 200

uv run python scripts/translate_benchmarks.py \
  --model ollama/qwen2.5-coder:7b \
  --count 200
```

### Step 2: Run Four-Way Ablation

```bash
# Run all 4 verification configurations for each model
# Configurations: none, structural_only, semantic_only, progressive

uv run python scripts/run_benchmarks.py \
  --model groq_llama-3.3-70b-versatile \
  --config progressive

# Repeat for all model × config combinations
```

### Step 3: Run LLM-as-a-Judge Baseline

```bash
# Run the Tautology Trap experiment
uv run python scripts/llm_judge_baseline.py
```

### Step 4: Generate Paper Tables

```bash
# Generate LaTeX-ready ablation and taxonomy tables
uv run python scripts/generate_tables.py
```

---

## Running Tests

```bash
# Run all tests
make test

# Run with verbose output
uv run pytest tests/ -v

# Run a specific test module
uv run pytest tests/test_matcher.py -v

# Run with coverage
uv run pytest tests/ --cov=src/neuroast --cov-report=term-missing
```

---

## Code Quality

```bash
# Lint
make lint

# Auto-format
make format
```

---

## Hallucination Taxonomy

NeuroAST classifies detected hallucinations into 11 categories:

| Phase | Category | Description |
|-------|----------|-------------|
| P1 | `Missing` | Source construct absent in target |
| P1 | `Invented` | Target construct with no source counterpart |
| P1 | `Depth_Mismatch` | Nesting level divergence between matched nodes |
| P1 | `Type_Change` | Control-flow node type changed (e.g., `for` → `while`) |
| P2 | `Lost_Data_Dep` | Def-use chain broken in target NormPDG |
| P2 | `Lost_Ctrl_Dep` | Control dependency lost across translation |
| P2 | `Invalid_Type` | Illegal type narrowing or widening |
| TE | `Idiom_Tolerated` | Valid language idiom (suppressed) |
| TE | `Alloc_Tolerated` | GC vs. manual memory (suppressed) |
| TE | `Iterator_Tolerated` | Enhanced for-each vs. index loop (suppressed) |
| TE | `Cast_Tolerated` | Equivalent numeric cast pattern (suppressed) |

---

## Experimental Results Summary

### Four-Way Ablation (200 programs per model)

| Model | None | Structural (P1) | Semantic (P2) | Progressive (P1+P2) | Avg Time |
|-------|------|-----------------|---------------|---------------------|----------|
| Llama-3.3-70B | 0 | 634 | 6 | **477** | 0.9 ms |
| Llama-3.1-8B | 0 | 1,202 | 15 | **951** | 0.8 ms |
| Qwen-2.5-Coder-7B | 0 | 1,798 | 33 | **1,438** | 0.9 ms |

### Taxonomy Distribution (Progressive)

| Category | Total | Percentage |
|----------|-------|------------|
| `Invented` | 1,715 | 60.1% |
| `Missing` | 652 | 22.8% |
| `Depth_Mismatch` | 499 | 17.5% |
| `Semantic (P2)` | 48 | ~1.7% |
| **Total** | **2,866** | |

---

## Docker Services

### Joern CPG Server

```bash
make joern-up       # Start Joern (background)
make joern-down     # Stop Joern
make joern-logs     # Tail server logs
make joern-status   # Check health + port binding
make joern-test     # Send test CPGQL query
```

**Resource allocation** (configurable in `docker-compose.yml`):
- CPU: 4 cores (limit), 1 core (reserved)
- Memory: 7 GB (limit), 1 GB (reserved)
- JVM Heap: 512 MB – 6 GB (G1GC)

---

## Paper

The accompanying research paper is in `Paper/`. To compile:

```bash
cd Paper
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Or upload the `Paper/` folder to [Overleaf](https://www.overleaf.com/) for cloud compilation.

---

## Citation

If you use NeuroAST in your research, please cite:

```bibtex
@inproceedings{hareesh2026neuroast,
  title     = {NeuroAST: Progressive Neuro-Symbolic Verification
               for Algorithmic Code Translation},
  author    = {Hareesh, T and Thushara, M.G. and Das, Abhinav C},
  booktitle = {Proceedings of the IEEE Conference},
  year      = {2026}
}
```

---

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [IBM Project CodeNet](https://github.com/IBM/Project_CodeNet) for the benchmark corpus
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/) for fast, incremental AST parsing
- [Joern](https://joern.io/) for Code Property Graph extraction
- [LiteLLM](https://github.com/BerriAI/litellm) for unified LLM API routing
- [Ollama](https://ollama.ai/) for local LLM inference
