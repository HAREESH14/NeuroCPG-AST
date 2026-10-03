"""
Tolerance Engine — Idiom vs Hallucination Classification (RC3).

Distinguishes valid idiom transformations from genuine hallucinations.
When Phase 1 flags a structural mismatch (e.g., missing for-loop),
this engine determines whether the change preserves semantics.

★ RESEARCH CONTRIBUTION RC3

Each tolerance rule encodes domain knowledge about which C→Java
transformations are semantically valid even though they change
program structure. The paper can present precision/recall curves
with and without tolerance rules.

Tolerance Rules Implemented:
    1. Loop → API Call Equivalence (for-loop → Arrays.fill, Collections.sort)
    2. Memory Model Normalization (malloc/free → new/GC)
    3. String Handling Idiom (char*/strcmp → String/.equals)
    4. Error Handling Idiom (return error_code → throw Exception)
"""

from __future__ import annotations

import logging
import re

from neuroast.verification.structures import (
    Hallucination,
    HallucinationCategory,
    NormPDG,
    ToleratedTransformation,
)

logger = logging.getLogger(__name__)


class ToleranceEngine:
    """Distinguishes valid idiom transformations from genuine hallucinations.

    ★ RESEARCH CONTRIBUTION RC3

    Parameters
    ----------
    enabled_rules:
        Names of tolerance rules to activate. Pass ``None`` for all rules.
        This parameter enables clean ablation studies — disable tolerance
        to measure the false positive rate of Phase 1 alone.
    """

    # Registry of all tolerance rules
    ALL_RULES = [
        "loop_to_api",
        "memory_model",
        "string_idiom",
        "error_handling",
    ]

    def __init__(
        self,
        enabled_rules: list[str] | None = None,
    ) -> None:
        # ``None``  -> activate all rules (default behaviour)
        # ``[]``    -> activate no rules at all (needed for the "no tolerance"
        #              condition of the leave-one-out ablation study)
        if enabled_rules is None:
            self.enabled_rules = set(self.ALL_RULES)
        else:
            self.enabled_rules = set(enabled_rules)

        unknown = self.enabled_rules - set(self.ALL_RULES)
        if unknown:
            # A silently ignored rule name would produce a "rule disabled"
            # ablation row that is indistinguishable from the full pipeline.
            logger.warning(
                "Unknown tolerance rule name(s) ignored: %s (known rules: %s)",
                sorted(unknown),
                self.ALL_RULES,
            )

        logger.info("Tolerance engine initialized with rules: %s", self.enabled_rules)

    def apply_tolerance(
        self,
        hallucinations: list[Hallucination],
        source_pdg: NormPDG | None = None,
        target_pdg: NormPDG | None = None,
        source_code: str = "",
        target_code: str = "",
    ) -> tuple[list[Hallucination], list[ToleratedTransformation]]:
        """Filter hallucinations by applying tolerance rules.

        Parameters
        ----------
        hallucinations:
            List of hallucinations detected by Phase 1 or Phase 2.
        source_pdg:
            NormPDG of the source (optional, for data-flow context).
        target_pdg:
            NormPDG of the target (optional, for data-flow context).
        source_code:
            Raw source code (for pattern matching).
        target_code:
            Raw target code (for pattern matching).

        Returns
        -------
        tuple
            - remaining_hallucinations: genuine hallucinations only
            - tolerated: list of valid transformations that were cleared
        """
        remaining: list[Hallucination] = []
        tolerated: list[ToleratedTransformation] = []

        for h in hallucinations:
            tolerance_result = self._try_tolerate(
                h,
                source_code=source_code,
                target_code=target_code,
                source_pdg=source_pdg,
                target_pdg=target_pdg,
            )

            if tolerance_result is not None:
                tolerated.append(tolerance_result)
                logger.debug(
                    "Tolerated: %s — rule=%s",
                    h.description,
                    tolerance_result.tolerance_rule,
                )
            else:
                remaining.append(h)

        logger.info(
            "Tolerance applied: %d hallucinations → %d genuine + %d tolerated",
            len(hallucinations),
            len(remaining),
            len(tolerated),
        )

        return remaining, tolerated

    def _try_tolerate(
        self,
        hallucination: Hallucination,
        source_code: str = "",
        target_code: str = "",
        source_pdg: NormPDG | None = None,
        target_pdg: NormPDG | None = None,
    ) -> ToleratedTransformation | None:
        """Try to match a hallucination to a tolerance rule.

        Returns a ToleratedTransformation if matched, None otherwise.
        """
        # Only apply to structural hallucinations (Phase 1 false positives)
        if not hallucination.category.is_structural:
            return None

        if "loop_to_api" in self.enabled_rules:
            result = self._check_loop_to_api(hallucination, source_code, target_code)
            if result:
                return result

        if "memory_model" in self.enabled_rules:
            result = self._check_memory_model(hallucination, source_code, target_code)
            if result:
                return result

        if "string_idiom" in self.enabled_rules:
            result = self._check_string_idiom(hallucination, source_code, target_code)
            if result:
                return result

        if "error_handling" in self.enabled_rules:
            result = self._check_error_handling(hallucination, source_code, target_code)
            if result:
                return result

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 1: Loop → API Call Equivalence
    # ─────────────────────────────────────────────────────────────────────────

    # Java API calls that can replace C for-loops
    LOOP_REPLACING_APIS = {
        "Arrays.fill",
        "Arrays.sort",
        "Arrays.copyOf",
        "Arrays.copyOfRange",
        "Arrays.equals",
        "Arrays.deepEquals",
        "Collections.sort",
        "Collections.reverse",
        "Collections.fill",
        "Collections.copy",
        "System.arraycopy",
        "Arrays.stream",
        "Arrays.asList",
    }

    def _check_loop_to_api(
        self,
        h: Hallucination,
        source_code: str,
        target_code: str,
    ) -> ToleratedTransformation | None:
        """Check if a missing loop was replaced by an equivalent Java API call.

        Rule: If source has a for/while loop operating on an array, and
        the target has an Arrays/Collections API call with the same effect,
        this is a valid idiom transformation.
        """
        if h.category != HallucinationCategory.MISSING:
            return None
        if h.node_type not in ("for_loop", "while_loop"):
            return None

        # Check if target uses any known loop-replacing APIs
        target_lower = target_code.lower()
        for api in self.LOOP_REPLACING_APIS:
            if api.lower() in target_lower:
                return ToleratedTransformation(
                    original_hallucination=h,
                    tolerance_rule="loop_to_api",
                    explanation=(
                        f"Missing {h.node_type} was replaced by {api} — "
                        f"a semantically equivalent Java API call."
                    ),
                )

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 2: Memory Model Normalization
    # ─────────────────────────────────────────────────────────────────────────

    def _check_memory_model(
        self,
        h: Hallucination,
        source_code: str,
        target_code: str,
    ) -> ToleratedTransformation | None:
        """Check if a missing function_call is a C memory operation.

        Rule: If the source calls malloc/calloc/free and the target
        doesn't (because Java uses new/GC), this is a valid transformation.
        """
        if h.category != HallucinationCategory.MISSING:
            return None
        if h.node_type != "function_call":
            return None

        # Check if the missing call is a memory management function
        c_memory_funcs = {"malloc", "calloc", "realloc", "free"}
        desc_lower = h.description.lower()

        for func in c_memory_funcs:
            if func in desc_lower or func in source_code:
                return ToleratedTransformation(
                    original_hallucination=h,
                    tolerance_rule="memory_model",
                    explanation=(
                        f"Missing '{func}' call is expected — Java uses "
                        f"'new' for allocation and garbage collection for deallocation."
                    ),
                )

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 3: String Handling Idiom
    # ─────────────────────────────────────────────────────────────────────────

    # C string functions and their Java equivalents
    # C string functions → Java equivalent patterns (for substring matching)
    # Each value is a list of patterns to check in the target code.
    C_TO_JAVA_STRING_MAP: dict[str, list[str]] = {
        "strcmp": [".equals(", ".compareTo("],
        "strncmp": [".equals(", ".regionMatches("],
        "strcpy": ["new String(", '= "'],
        "strcat": [".concat(", "+ "],
        "strlen": [".length("],
        "strstr": [".contains(", ".indexOf("],
        "strchr": [".indexOf("],
        "sprintf": ["String.format("],
        "snprintf": ["String.format("],
    }

    def _check_string_idiom(
        self,
        h: Hallucination,
        source_code: str,
        target_code: str,
    ) -> ToleratedTransformation | None:
        """Check if a structural change is a C→Java string idiom transformation.

        Rule: If source uses char[]/strcmp/strcat and target uses
        String/.equals()/.concat(), this is a valid idiom.
        """
        if h.category not in (HallucinationCategory.MISSING, HallucinationCategory.INVENTED):
            return None

        # Check if C source uses string functions
        for c_func, java_patterns in self.C_TO_JAVA_STRING_MAP.items():
            if c_func in source_code and any(pattern in target_code for pattern in java_patterns):
                java_equiv = " / ".join(java_patterns)
                return ToleratedTransformation(
                    original_hallucination=h,
                    tolerance_rule="string_idiom",
                    explanation=(
                        f"C string function '{c_func}' → Java '{java_equiv}' "
                        f"is a valid idiom transformation."
                    ),
                )

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 4: Error Handling Idiom
    # ─────────────────────────────────────────────────────────────────────────

    def _check_error_handling(
        self,
        h: Hallucination,
        source_code: str,
        target_code: str,
    ) -> ToleratedTransformation | None:
        """Check if error handling idiom changed (return code → exception).

        Rule: If source uses return error_code (int) and target uses
        throw Exception, this is a valid C→Java error handling idiom.
        """
        # Check for invented try-catch blocks
        if h.category == HallucinationCategory.INVENTED and h.node_type == "try_catch":
            # Check if the C source uses error-return patterns
            error_patterns = [
                r"return\s*-\d+",  # return -1
                r"return\s+NULL",  # return NULL
                r"return\s+0\s*;",  # return 0 (sometimes error)
                r"perror\s*\(",  # perror()
                r"errno",  # errno usage
                r"if\s*\([^)]*==\s*NULL",  # if (ptr == NULL)
                r"if\s*\([^)]*<\s*0",  # if (result < 0)
            ]

            for pattern in error_patterns:
                if re.search(pattern, source_code):
                    return ToleratedTransformation(
                        original_hallucination=h,
                        tolerance_rule="error_handling",
                        explanation=(
                            "Invented try-catch block corresponds to C error-return pattern. "
                            "C uses return codes for error handling; Java uses exceptions."
                        ),
                    )

        # Check for missing return statements (replaced by throw)
        if (
            h.category == HallucinationCategory.MISSING
            and h.node_type == "return"
            and ("throw" in target_code or "Exception" in target_code)
        ):
            return ToleratedTransformation(
                original_hallucination=h,
                tolerance_rule="error_handling",
                explanation=(
                    "Missing return statement was replaced by throw Exception — "
                    "valid C→Java error handling idiom transformation."
                ),
            )

        return None
