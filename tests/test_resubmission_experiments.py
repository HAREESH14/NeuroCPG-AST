"""Tests for the Round-2 resubmission experiment scripts.

Covers:
  * ``scripts/resubmission_ted_sensitivity.py``   (Reviewer 2, Comment 4)
  * ``scripts/resubmission_tolerance_ablation.py`` (Reviewer 2, Comment 4)
  * ``scripts/resubmission_judge_repeats.py``      (Reviewer 2, Comment 6)
  * ``scripts/resubmission_reproducibility_facts.py`` (Reviewer 2, Comment 2)
  * the ``ToleranceEngine`` rule-selection fix that makes ablation possible
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the experiment scripts the same way tests/test_independent_judge.py does.
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import resubmission_judge_repeats as judge_repeats  # noqa: E402
import resubmission_reproducibility_facts as repro_facts  # noqa: E402
import resubmission_ted_sensitivity as ted  # noqa: E402
import resubmission_tolerance_ablation as ablation  # noqa: E402
from neuroast.neural.prompts import format_judge_prompt  # noqa: E402
from neuroast.verification.tolerance import ToleranceEngine  # noqa: E402


def _fake_response(content: str) -> MagicMock:
    """Build a litellm-shaped mock completion response."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    return response


# ── Matched-prompt guarantee ───────────────────────────────────────────────


class TestJudgePromptIsShared:
    """All judge experiments must use one identical prompt (Reviewer 2, C6)."""

    @patch("llm_judge_baseline.litellm.completion")
    def test_self_judge_baseline_uses_canonical_prompt(self, mock_completion: MagicMock) -> None:
        import llm_judge_baseline

        original = os.environ.get("OLLAMA_API_BASE")
        mock_completion.return_value = _fake_response(
            '{"hallucinations_found": 0, "is_equivalent": true, "explanation": "ok"}'
        )

        llm_judge_baseline.judge_translation(c_code="int main(){}", java_code="class A{}")

        assert mock_completion.call_args[1]["messages"] == format_judge_prompt(
            "int main(){}", "class A{}"
        )
        if original is None:
            os.environ.pop("OLLAMA_API_BASE", None)
        else:
            os.environ["OLLAMA_API_BASE"] = original

    @patch("resubmission_independent_judge.litellm.completion")
    def test_independent_judge_uses_canonical_prompt(
        self, mock_completion: MagicMock
    ) -> None:
        import resubmission_independent_judge

        mock_completion.return_value = _fake_response(
            '{"hallucinations_found": 1, "is_equivalent": false, "explanation": "bad"}'
        )

        resubmission_independent_judge.judge_translation(
            "int main(){}",
            "class A{}",
            "ollama/llama3.1:8b",
            ollama_url="http://localhost:11434",
        )

        assert mock_completion.call_args[1]["messages"] == format_judge_prompt(
            "int main(){}", "class A{}"
        )

    def test_canonical_prompt_contains_required_schema(self) -> None:
        messages = format_judge_prompt("C", "J")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "hallucinations_found" in messages[0]["content"]
        assert "is_equivalent" in messages[0]["content"]

    def test_repeats_script_uses_canonical_prompt(self) -> None:
        assert judge_repeats.format_judge_prompt is format_judge_prompt


# ── TED threshold sensitivity ──────────────────────────────────────────────


class TestTedSensitivity:
    def test_sweep_counts_flags_clean_and_misses(self) -> None:
        scores = {"a.c": 0.0, "b.c": 3.0, "c.c": 5.0, "d.c": None}
        verdicts = {"a.c": 0, "b.c": 4, "c.c": 0, "d.c": 2}

        row = ted.sweep_threshold(scores, verdicts, threshold=2)

        assert row["files_scored"] == 3  # None-scored pair excluded
        assert row["flagged"] == 2  # b.c (3 > 2) and c.c (5 > 2)
        assert row["flag_rate"] == round(2 / 3, 4)
        assert row["neuroast_clean_files"] == 2  # a.c, c.c
        assert row["neuroast_clean_flagged"] == 1  # c.c wrongly flagged
        assert row["fp_rate_vs_clean"] == 0.5
        assert row["neuroast_flagged_files"] == 1  # b.c
        assert row["missed_by_baseline"] == 0
        assert row["agreement_rate"] == round(2 / 3, 4)  # a.c, b.c agree

    def test_sweep_ignores_files_without_neuroast_verdict(self) -> None:
        row = ted.sweep_threshold({"a.c": 9.0}, {}, threshold=2)
        assert row["files_scored"] == 0
        assert row["flag_rate"] == 0.0

    def test_higher_threshold_flags_fewer_files(self) -> None:
        scores = {"a.c": 1.0, "b.c": 2.0, "c.c": 4.0}
        verdicts = {"a.c": 1, "b.c": 1, "c.c": 1}

        counts = [
            ted.sweep_threshold(scores, verdicts, threshold=t)["flagged"]
            for t in (1, 2, 3, 5)
        ]
        assert counts == [2, 1, 1, 0]

    def test_build_summary_aggregates_models(self) -> None:
        ted_scores = {
            "m1": {"a.c": 5.0},
            "m2": {"a.c": 0.0, "b.c": 5.0},
        }
        verdicts = {"m1": {"a.c": 1}, "m2": {"a.c": 1, "b.c": 1}}

        summary = ted.build_summary(ted_scores, verdicts, [2])

        overall = summary["2"]["overall"]
        assert overall["files_scored"] == 3
        assert overall["flagged"] == 2
        assert set(summary["2"]["per_model"]) == {"m1", "m2"}

    def test_zero_threshold_sensitivity_table_is_serialisable(self) -> None:
        summary = ted.build_summary({"m": {"a.c": 1.0}}, {"m": {"a.c": 0}}, [1])
        assert "1" in summary
        assert summary["1"]["overall"]["fp_rate_vs_clean"] == 0.0


# ── Tolerance Engine ablation ──────────────────────────────────────────────


class TestToleranceRuleSelection:
    """``enabled_rules`` must distinguish "all rules" from "no rules"."""

    def test_none_means_all_rules(self) -> None:
        engine = ToleranceEngine()
        assert engine.enabled_rules == set(ToleranceEngine.ALL_RULES)

    def test_empty_list_means_no_rules(self) -> None:
        engine = ToleranceEngine(enabled_rules=[])
        assert engine.enabled_rules == set()

    def test_explicit_subset(self) -> None:
        engine = ToleranceEngine(enabled_rules=["memory_model"])
        assert engine.enabled_rules == {"memory_model"}

    def test_unknown_rule_is_retained_but_warned_about(self) -> None:
        engine = ToleranceEngine(enabled_rules=["not_a_rule"])
        assert engine.enabled_rules == {"not_a_rule"}

    def test_no_rules_engine_suppresses_nothing(self) -> None:
        engine = ToleranceEngine(enabled_rules=[])
        remaining, tolerated = engine.apply_tolerance([], source_code="", target_code="")
        assert remaining == []
        assert tolerated == []


class TestToleranceAblation:
    def test_build_rule_configs_has_all_none_and_leave_one_out(self) -> None:
        configs = ablation.build_rule_configs(["r1", "r2"])
        names = [name for name, _rules in configs]

        assert names[0] == "all_rules"
        assert names[1] == "no_tolerance"
        assert set(names[2:]) == {"minus_r1", "minus_r2"}
        assert dict(configs)["no_tolerance"] == []
        assert dict(configs)["minus_r1"] == ["r2"]

    def test_aggregate_models_computes_additional_flags(self) -> None:
        per_model = {
            "m1": {
                "files_scored": 2,
                "raw_phase1_hallucinations": 10,
                "conditions": {
                    "all_rules": {"remaining": 8},
                    "no_tolerance": {"remaining": 10},
                    "minus_r1": {"remaining": 9},
                },
            }
        }
        aggregate = ablation.aggregate_models(per_model, ["all_rules", "no_tolerance", "minus_r1"])

        assert aggregate["files_scored"] == 2
        assert aggregate["raw_phase1_hallucinations"] == 10
        assert aggregate["conditions"]["all_rules"]["remaining"] == 8
        assert aggregate["conditions"]["all_rules"]["suppression_rate"] == 0.2
        assert aggregate["conditions"]["no_tolerance"]["additional_flags_vs_all_rules"] == 2
        assert aggregate["conditions"]["minus_r1"]["additional_flags_vs_all_rules"] == 1


# ── Repeated-trial judge experiment ────────────────────────────────────────


class TestJudgeJsonExtraction:
    def test_plain_json(self) -> None:
        parsed = judge_repeats._extract_json('{"hallucinations_found": 2}')
        assert parsed["hallucinations_found"] == 2

    def test_markdown_fenced_json(self) -> None:
        raw = '```json\n{"hallucinations_found": 0, "is_equivalent": true}\n```'
        assert judge_repeats._extract_json(raw)["is_equivalent"] is True

    def test_json_with_surrounding_prose(self) -> None:
        raw = 'Here is my verdict:\n{"hallucinations_found": 1}\nHope that helps.'
        assert judge_repeats._extract_json(raw)["hallucinations_found"] == 1

    def test_unparseable_returns_sentinel(self) -> None:
        assert judge_repeats._extract_json("no json here")["_parse_failed"] is True


class TestJudgeClassification:
    def test_classifications(self) -> None:
        assert judge_repeats.classify(3, 1) == "AGREE_FLAGGED"
        assert judge_repeats.classify(3, 0) == "JUDGE_MISSED"
        assert judge_repeats.classify(0, 1) == "JUDGE_FALSE_ALARM"
        assert judge_repeats.classify(0, 0) == "AGREE_CLEAN"

    def test_unparseable_response_is_parse_error(self) -> None:
        assert (
            judge_repeats.classify(3, -1, "PARSE_FAILED: I cannot answer.")
            == "PARSE_ERROR"
        )

    def test_failed_api_call_is_api_error_not_parse_error(self) -> None:
        assert (
            judge_repeats.classify(3, -1, "API_ERROR: RateLimitError: 429")
            == "API_ERROR"
        )


class TestJudgeTrialSummary:
    def _records(self) -> list[dict]:
        return [
            {"classification": "AGREE_FLAGGED", "latency_ms": 10.0, "cost_usd": 0.01},
            {"classification": "AGREE_FLAGGED", "latency_ms": 20.0, "cost_usd": 0.01},
            {"classification": "JUDGE_MISSED", "latency_ms": 30.0, "cost_usd": 0.01},
            {"classification": "JUDGE_FALSE_ALARM", "latency_ms": None, "cost_usd": None},
            {"classification": "AGREE_CLEAN", "latency_ms": 40.0, "cost_usd": 0.01},
            {"classification": "PARSE_ERROR", "latency_ms": 5.0, "cost_usd": None},
        ]

    def test_summary_metrics(self) -> None:
        summary = judge_repeats.summarise_trial(self._records())

        assert summary["files"] == 6
        assert summary["parse_errors"] == 1
        assert summary["api_errors"] == 0
        assert summary["recall_among_parsed_pct"] == round(2 / 3 * 100, 1)
        # Conservative bound counts the parse failure as a miss.
        assert summary["recall_lower_bound_pct"] == round(2 / 4 * 100, 1)
        assert summary["false_alarm_rate_pct"] == 50.0
        assert summary["latency_mean_ms"] == 21.0
        assert summary["latency_median_ms"] == 20.0
        assert summary["total_cost_usd"] == 0.04

    def test_api_errors_are_tracked_separately(self) -> None:
        records = [
            {"classification": "AGREE_FLAGGED", "latency_ms": 10.0, "cost_usd": 0.01},
            {"classification": "JUDGE_MISSED", "latency_ms": 10.0, "cost_usd": 0.01},
            {"classification": "API_ERROR", "latency_ms": None, "cost_usd": None},
            {"classification": "API_ERROR", "latency_ms": None, "cost_usd": None},
        ]
        summary = judge_repeats.summarise_trial(records)

        assert summary["api_errors"] == 2
        assert summary["parse_errors"] == 0
        assert summary["api_error_rate"] == 0.5
        # 1 of 4 files answered "flagged"; the two API failures count as misses.
        assert summary["recall_among_parsed_pct"] == 50.0
        assert summary["recall_lower_bound_pct"] == round(1 / 4 * 100, 1)

    def test_summary_of_empty_trial(self) -> None:
        summary = judge_repeats.summarise_trial([])
        assert summary["files"] == 0
        assert summary["recall_among_parsed_pct"] == 0.0
        assert summary["latency_mean_ms"] is None

    def test_aggregate_reports_mean_and_std(self) -> None:
        trial_a = judge_repeats.summarise_trial(self._records())
        trial_b = judge_repeats.summarise_trial(self._records()[:2])

        aggregate = judge_repeats.aggregate_trials([trial_a, trial_b])

        recall = aggregate["recall_among_parsed_pct"]
        assert aggregate["trials"] == 2
        assert recall["per_trial"] == [
            round(trial_a["recall_among_parsed_pct"], 2),
            round(trial_b["recall_among_parsed_pct"], 2),
        ]
        assert recall["mean"] == round(sum(recall["per_trial"]) / 2, 2)
        assert recall["std"] >= 0.0
        assert len(aggregate["false_alarm_per_trial"]) == 2

    def test_aggregate_with_single_trial_has_zero_std(self) -> None:
        aggregate = judge_repeats.aggregate_trials(
            [judge_repeats.summarise_trial(self._records())]
        )
        assert aggregate["latency_mean_ms"]["std"] == 0.0


class TestJudgeProviderConfig:
    def test_ollama_sets_local_api_base(self) -> None:
        kwargs = judge_repeats._completion_kwargs(
            "ollama/llama3.1:8b", "http://localhost:11434"
        )
        assert kwargs["api_base"] == "http://localhost:11434"
        assert kwargs["model"] == "ollama/llama3.1:8b"

    def test_hosted_model_has_no_api_base_override(self) -> None:
        kwargs = judge_repeats._completion_kwargs(
            "gemini/gemini-2.5-flash", "http://localhost:11434"
        )
        assert "api_base" not in kwargs

    def test_self_judge_is_detected_by_model_identity(self) -> None:
        assert judge_repeats.TRANSLATOR_MODEL in judge_repeats.DEFAULT_JUDGE_MODELS


class TestDotenvLoading:
    def test_load_dotenv_does_not_clobber_existing_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("NEUROAST_TEST_KEY=from_file\n")

        os.environ["NEUROAST_TEST_KEY"] = "from_environment"
        judge_repeats._load_dotenv(env_file)
        assert os.environ["NEUROAST_TEST_KEY"] == "from_environment"

        del os.environ["NEUROAST_TEST_KEY"]
        judge_repeats._load_dotenv(env_file)
        assert os.environ["NEUROAST_TEST_KEY"] == "from_file"
        del os.environ["NEUROAST_TEST_KEY"]

    def test_load_dotenv_ignores_comments_and_blank_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# a comment\n\n\n")
        judge_repeats._load_dotenv(env_file)  # must not raise


class TestJudgeAsyncCall:
    @patch("resubmission_judge_repeats.litellm.acompletion")
    async def test_judge_call_parses_fenced_response(
        self, mock_acompletion: MagicMock
    ) -> None:
        mock_acompletion.return_value = _fake_response(
            '```json\n{"hallucinations_found": 4, "is_equivalent": false, '
            '"explanation": "extra loop"}\n```'
        )

        report = await judge_repeats.judge_translation_async(
            "int main(){}", "class A{}", "ollama/llama3.1:8b"
        )

        assert report["hallucinations_found"] == 4
        assert report["is_equivalent"] is False
        assert report["latency_ms"] is not None

    @patch("resubmission_judge_repeats.litellm.acompletion")
    async def test_judge_call_records_parse_failure(
        self, mock_acompletion: MagicMock
    ) -> None:
        mock_acompletion.return_value = _fake_response("I cannot answer that.")

        report = await judge_repeats.judge_translation_async(
            "int main(){}", "class A{}", "ollama/llama3.1:8b"
        )

        assert report["hallucinations_found"] == -1
        assert report["explanation"].startswith("PARSE_FAILED")

    @patch("resubmission_judge_repeats.litellm.acompletion")
    async def test_judge_call_survives_api_error(
        self, mock_acompletion: MagicMock
    ) -> None:
        mock_acompletion.side_effect = RuntimeError("boom")

        report = await judge_repeats.judge_translation_async(
            "int main(){}", "class A{}", "gemini/gemini-2.5-flash", max_retries=0
        )

        assert report["hallucinations_found"] == -1
        assert report["explanation"].startswith("API_ERROR")
        assert report["latency_ms"] is None


# ── Reproducibility fact sheet ─────────────────────────────────────────────


class TestReproducibilityFacts:
    def test_translation_decoding_matches_experiment_entry_point(self) -> None:
        # scripts/translate_benchmarks.py constructs Translator(temperature=0.1),
        # overriding the 0.2 library default -- the paper must state 0.1.
        assert repro_facts.TRANSLATION_DECODING["temperature"] == 0.1
        assert repro_facts.TRANSLATION_DECODING["max_tokens"] == 4096

    def test_five_audited_categories_are_documented(self) -> None:
        assert len(repro_facts.CATEGORY_DEFINITIONS) == 5
        assert set(repro_facts.CATEGORY_DEFINITIONS) == {
            "invented",
            "missing",
            "depth_mismatch",
            "lost_control_dep",
            "invalid_type_transform",
        }

    def test_model_registry_matches_result_directories(self) -> None:
        dirs = {entry["result_dir"] for entry in repro_facts.MODEL_REGISTRY}
        assert dirs == {
            "groq_llama-3.1-8b-instant",
            "groq_llama-3.3-70b-versatile",
            "ollama_llama3.1_8b",
            "ollama_qwen2.5-coder_7b",
        }
        for entry in repro_facts.MODEL_REGISTRY:
            assert "/" in entry["litellm_id"]

    def test_fact_sheet_contains_prompts_and_decoding(self, monkeypatch) -> None:
        # Avoid re-parsing 600 files during the unit test.
        monkeypatch.setattr(
            repro_facts, "measure_parse_failures", lambda dirs: {"stub": {}}
        )
        monkeypatch.setattr(repro_facts, "pipeline_attempt_stats", lambda dirs: {})

        fact_sheet = repro_facts.build_fact_sheet()

        assert fact_sheet["translation_direction"] == "C -> Java"
        assert fact_sheet["translation_prompts"]["system_prompt"]
        assert "Translate the following C program to Java" in (
            fact_sheet["translation_prompts"]["user_prompt_template"]
        )
        assert "hallucinations_found" in fact_sheet["judge_protocol"]["prompt"]
        assert fact_sheet["judge_protocol"]["decoding"]["temperature"] is None
        assert fact_sheet["parsing"]["per_model"] == {"stub": {}}
