"""Tests for neuroast.utils.metrics — experiment metrics collection and export."""

import csv
import json
from pathlib import Path

from neuroast.utils.metrics import BenchmarkRecord, MetricsCollector
from neuroast.verification.structures import (
    AlignmentReport,
    ControlFlowGraph,
    Hallucination,
    HallucinationCategory,
    HallucinationSeverity,
    PipelineResult,
    TranslationAttempt,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_report(
    aligned: bool = True,
    confidence: float = 1.0,
    hallucinations: list[Hallucination] | None = None,
) -> AlignmentReport:
    return AlignmentReport(
        is_aligned=aligned,
        confidence=confidence,
        hallucinations=hallucinations or [],
        source_summary={"function": 1, "for_loop": 2},
        target_summary={"function": 1, "for_loop": 2},
    )


def _make_pipeline_result(
    success: bool = True,
    confidence: float = 1.0,
    attempts: int = 1,
    hallucinations: list[Hallucination] | None = None,
    model: str = "groq/llama-3.3-70b-versatile",
    total_time_ms: float = 123.4,
) -> PipelineResult:
    report = _make_report(aligned=success, confidence=confidence, hallucinations=hallucinations)
    return PipelineResult(
        success=success,
        source_code="int main() {}",
        java_code="public class Main {}",
        attempts=attempts,
        source_cfg=ControlFlowGraph(language="c"),
        final_report=report,
        attempt_history=[
            TranslationAttempt(
                attempt_number=1,
                java_code="public class Main {}",
                alignment_report=report,
            ),
        ],
        model=model,
        total_time_ms=total_time_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# BenchmarkRecord
# ─────────────────────────────────────────────────────────────────────────────


class TestBenchmarkRecord:
    def test_from_successful_pipeline(self) -> None:
        result = _make_pipeline_result(success=True, confidence=0.98)
        record = BenchmarkRecord.from_pipeline_result(result, source_file="sort.c")
        assert record.source_file == "sort.c"
        assert record.success is True
        assert record.final_confidence == 0.98
        assert record.total_hallucinations == 0
        assert record.structural_hallucinations == 0

    def test_from_failed_pipeline(self) -> None:
        halls = [
            Hallucination(
                category=HallucinationCategory.MISSING,
                severity=HallucinationSeverity.CRITICAL,
                node_type="for_loop",
                description="Missing loop",
            ),
            Hallucination(
                category=HallucinationCategory.INVENTED,
                severity=HallucinationSeverity.WARNING,
                node_type="try_catch",
                description="Invented try",
            ),
        ]
        result = _make_pipeline_result(
            success=False, confidence=0.3, attempts=3, hallucinations=halls
        )
        record = BenchmarkRecord.from_pipeline_result(result, source_file="io.c")
        assert record.success is False
        assert record.total_hallucinations == 2
        assert record.hallucination_categories == {"missing": 1, "invented": 1}

    def test_category_counting(self) -> None:
        halls = [
            Hallucination(
                category=HallucinationCategory.MISSING,
                node_type="for_loop",
                description="a",
            ),
            Hallucination(
                category=HallucinationCategory.MISSING,
                node_type="while_loop",
                description="b",
            ),
            Hallucination(
                category=HallucinationCategory.DEPTH_MISMATCH,
                node_type="function",
                description="c",
            ),
        ]
        result = _make_pipeline_result(success=False, confidence=0.4, hallucinations=halls)
        record = BenchmarkRecord.from_pipeline_result(result)
        assert record.hallucination_categories["missing"] == 2
        assert record.hallucination_categories["depth_mismatch"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# MetricsCollector
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricsCollector:
    def test_add_and_count(self) -> None:
        collector = MetricsCollector(experiment_name="test_exp")
        collector.add(_make_pipeline_result(success=True), source_file="a.c")
        collector.add(_make_pipeline_result(success=False, confidence=0.5), source_file="b.c")
        assert len(collector.records) == 2

    def test_summarize_empty(self) -> None:
        collector = MetricsCollector()
        summary = collector.summarize()
        assert summary.total_programs == 0
        assert summary.success_rate == 0.0

    def test_summarize_mixed(self) -> None:
        collector = MetricsCollector(experiment_name="ablation")
        collector.add(
            _make_pipeline_result(success=True, confidence=1.0, total_time_ms=100.0),
            source_file="a.c",
        )
        collector.add(
            _make_pipeline_result(success=True, confidence=0.96, total_time_ms=200.0),
            source_file="b.c",
        )
        collector.add(
            _make_pipeline_result(
                success=False,
                confidence=0.3,
                attempts=3,
                hallucinations=[
                    Hallucination(
                        category=HallucinationCategory.MISSING,
                        node_type="for_loop",
                        description="x",
                    ),
                ],
                total_time_ms=500.0,
            ),
            source_file="c.c",
        )

        summary = collector.summarize()
        assert summary.total_programs == 3
        assert summary.successful_translations == 2
        assert abs(summary.success_rate - 2 / 3) < 0.01
        assert summary.total_hallucinations == 1
        assert abs(summary.avg_time_ms - 266.67) < 1.0

    def test_add_from_report(self) -> None:
        collector = MetricsCollector()
        report = _make_report(aligned=True, confidence=0.99)
        record = collector.add_from_report(
            report, source_file="test.c", model="gpt-4", total_time_ms=50.0
        )
        assert record.success is True
        assert record.model == "gpt-4"
        assert len(collector.records) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────


class TestExport:
    def test_export_json(self, tmp_path: Path) -> None:
        collector = MetricsCollector(experiment_name="json_test")
        collector.add(_make_pipeline_result(success=True, confidence=0.99), source_file="a.c")
        collector.add(
            _make_pipeline_result(
                success=False,
                confidence=0.4,
                hallucinations=[
                    Hallucination(
                        category=HallucinationCategory.MISSING,
                        node_type="for_loop",
                        description="x",
                    ),
                ],
            ),
            source_file="b.c",
        )

        out = tmp_path / "results.json"
        collector.export_json(out)

        data = json.loads(out.read_text())
        assert data["experiment"] == "json_test"
        assert data["summary"]["total_programs"] == 2
        assert len(data["records"]) == 2
        assert data["records"][0]["source_file"] == "a.c"
        assert data["records"][1]["success"] is False

    def test_export_csv(self, tmp_path: Path) -> None:
        collector = MetricsCollector(experiment_name="csv_test")
        collector.add(_make_pipeline_result(success=True), source_file="a.c")
        collector.add(
            _make_pipeline_result(
                success=False,
                confidence=0.5,
                hallucinations=[
                    Hallucination(
                        category=HallucinationCategory.MISSING,
                        node_type="for_loop",
                        description="x",
                    ),
                    Hallucination(
                        category=HallucinationCategory.INVENTED,
                        node_type="try_catch",
                        description="y",
                    ),
                ],
            ),
            source_file="b.c",
        )

        out = tmp_path / "results.csv"
        collector.export_csv(out)

        with out.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["source_file"] == "a.c"
        assert rows[0]["success"] == "True"
        assert rows[1]["source_file"] == "b.c"
        assert rows[1]["success"] == "False"
        # Category columns should exist
        assert "cat_missing" in rows[0]
        assert int(rows[1]["cat_missing"]) == 1
        assert int(rows[1]["cat_invented"]) == 1

    def test_to_csv_string(self) -> None:
        collector = MetricsCollector()
        collector.add(_make_pipeline_result(success=True), source_file="test.c")
        csv_str = collector.to_csv_string()
        assert "source_file" in csv_str
        assert "test.c" in csv_str

    def test_export_empty(self, tmp_path: Path) -> None:
        collector = MetricsCollector()
        collector.export_csv(tmp_path / "empty.csv")
        assert not (tmp_path / "empty.csv").exists()  # No file created for empty

    def test_export_json_creates_dirs(self, tmp_path: Path) -> None:
        collector = MetricsCollector()
        collector.add(_make_pipeline_result(), source_file="x.c")
        nested = tmp_path / "deep" / "nested" / "results.json"
        collector.export_json(nested)
        assert nested.exists()
