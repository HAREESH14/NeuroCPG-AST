"""
Prompt templates for LLM translation and repair.

All prompts are centralized here for easy iteration — this is
critical for a research project where prompt engineering directly
affects hallucination rates.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Translation Prompts
# ─────────────────────────────────────────────────────────────────────────────

TRANSLATION_SYSTEM_PROMPT = """\
You are an expert C-to-Java code translator. Your goal is to produce \
a functionally equivalent Java translation of the given C program.

Rules:
1. Preserve all control-flow structures (loops, branches, switch-case) exactly.
2. Map C functions to Java static methods inside a public class.
3. Map C arrays to Java arrays.
4. Map printf/scanf to System.out.println/Scanner as appropriate.
5. Do NOT add try-catch blocks unless the C code has explicit error handling.
6. Do NOT change loop types (for→while, while→for) unless absolutely necessary.
7. Do NOT drop any loops, branches, or return statements.
8. Output ONLY the Java code — no explanations, no markdown fences.\
"""

TRANSLATION_USER_PROMPT = """\
Translate the following C program to Java:

```c
{source_code}
```

Output only the complete Java class. No explanations.\
"""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Targeted Repair Prompts
# ─────────────────────────────────────────────────────────────────────────────

REPAIR_SYSTEM_PROMPT = """\
You are a code repair agent. A structural verification system has detected \
specific issues in a Java translation. You must fix ONLY the listed issues \
without changing anything else.\
"""

REPAIR_USER_PROMPT = """\
Your previous Java translation has {n_hallucinations} structural error(s) \
detected by our verification system:

{hallucination_report}

Original C source:
```c
{source_code}
```

Your previous (incorrect) Java translation:
```java
{previous_translation}
```

Fix ONLY the identified structural issues. Preserve everything else exactly. \
Output only the corrected Java code — no explanations, no markdown fences.\
"""


def format_translation_prompt(source_code: str) -> list[dict[str, str]]:
    """Build the messages list for a translation request."""
    return [
        {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": TRANSLATION_USER_PROMPT.format(source_code=source_code),
        },
    ]


def format_repair_prompt(
    source_code: str,
    previous_translation: str,
    hallucination_report: str,
    n_hallucinations: int,
) -> list[dict[str, str]]:
    """Build the messages list for a targeted repair request."""
    return [
        {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": REPAIR_USER_PROMPT.format(
                source_code=source_code,
                previous_translation=previous_translation,
                hallucination_report=hallucination_report,
                n_hallucinations=n_hallucinations,
            ),
        },
    ]
