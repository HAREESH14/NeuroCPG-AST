Viewed README.md

Let me review your research context fully before answering.

Viewed activeContext.md:1-17
Viewed a5.md:1-80
Viewed implementation_plan.md:1-488
Viewed a5.md:80-250
Listed directory neuroast
Listed directory chat_history
Viewed a5.md:250-450
Viewed relatedworks.md:1-73
Listed directory neural
Viewed a5.md:450-657

Now I have the full picture. Let me create a comprehensive roadmap document.

Edited research_roadmap.md

Here's the honest picture, Hareesh:

## Where you stand

You've built **all the algorithms** — 94 tests pass, every research contribution (RC1–RC5) is implemented in code. But you have **zero real experimental data** yet. The code is the instrument; you haven't run the experiment.

## Your novelty in one line

> **Every existing CPG+LLM system flows CPG→LLM** (CPG helps the LLM). **You're the first to go LLM→CPG** (CPG verifies what the LLM generated). Nobody has used PDG comparison to detect hallucinations in code translations.

## The 5 things left to do

| # | What | Time | Why it matters |
|---|------|------|---------------|
| **1** | Get Joern Docker running + test CPG pipeline end-to-end | 1-2h | Without this, Phase 2 is untested theory |
| **2** | Translate all 49 benchmarks via LLM (Groq/GPT-4o) | 2-3h | This is your raw experimental data |
| **3** | Run the 4-way ablation (none / Phase 1 / Phase 2 / Progressive) | 3-4h | This fills your paper's results table |
| **4** | Analyze hallucination taxonomy distribution | 2-3h | This is the most *publishable* result |
| **5** | Write the paper | 1-2 weeks | Target ICSE/ASE 2027 |

## My recommendation: Start with Milestone 1 (Joern) + Milestone 2 (LLM translations) **in parallel** — they're independent and unblock everything.

Please review the detailed roadmap artifact and tell me which milestone you want to tackle first.