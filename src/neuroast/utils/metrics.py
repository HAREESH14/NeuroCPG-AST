"""
Metrics collection and export for NeuroAST experiments.

Collects hallucination rates, verification overhead, repair iteration
counts, and confidence distributions — everything needed for the
paper's results tables and figures.

Exports to JSON (machine-readable) and CSV (for pandas/matplotlib).
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from neuroast.verification.structures import (
    AlignmentReport,
    PipelineResult,
)

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkRecord:
    """A single benchmark evaluation record.

    Captures everything about one C→Java translation + verification run
    in a flat format suitable for tabular export.
    """

    source_file: str
    model: str
    success: bool
    attempts: int
    final_confidence: float
    total_hallucinations: int
    structural_hallucinations: int
    semantic_hallucinations: int
    tolerated_idioms: int
    total_time_ms: float
    hallucination_categories: dict[str, int] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # NEW — principled similarity metrics (None if not computed)
    tree_edit_distance: int | None = None
    tree_similarity: float | None = None
    data_flow_jaccard: float | None = None
    control_dep_jaccard: float | None = None
    tversky_index: float | None = None

    @classmethod
    def from_pipeline_result(
        cls,
        result: PipelineResult,
        source_file: str = "",
    ) -> BenchmarkRecord:
        """Create a BenchmarkRecord from a PipelineResult."""
        report = result.final_report

        # Count by category
        cat_counts: dict[str, int] = {}
        for h in report.hallucinations:
            key = h.category.value
            cat_counts[key] = cat_counts.get(key, 0) + 1

        return cls(
            source_file=source_file,
            model=result.model,
            success=result.success,
            attempts=result.attempts,
            final_confidence=report.confidence,
            total_hallucinations=len(report.hallucinations),
            structural_hallucinations=len(report.structural_hallucinations),
            semantic_hallucinations=len(report.semantic_hallucinations),
            tolerated_idioms=len(report.tolerated_idioms),
            total_time_ms=result.total_time_ms,
            hallucination_categories=cat_counts,
        )


@dataclass
class ExperimentSummary:
    """Aggregate statistics across multiple benchmark runs.

    Used for the paper's main results table.
    """

    total_programs: int = 0
    successful_translations: int = 0
    total_hallucinations: int = 0
    hallucinations_by_category: dict[str, int] = field(default_factory=dict)
    avg_confidence: float = 0.0
    avg_attempts: float = 0.0
    avg_time_ms: float = 0.0
    success_rate: float = 0.0


class MetricsCollector:
    """Collects and aggregates benchmark metrics for experiment analysis.

    Usage::

        collector = MetricsCollector(experiment_name="ablation_phase1_only")

        for result in pipeline_results:
            collector.add(result, source_file="bubble_sort.c")

        collector.export_json(Path("results/phase1_only.json"))
        collector.export_csv(Path("results/phase1_only.csv"))
        summary = collector.summarize()
    """

    def __init__(self, experiment_name: str = "default") -> None:
        self.experiment_name = experiment_name
        self.records: list[BenchmarkRecord] = []

    def add(
        self,
        result: PipelineResult,
        source_file: str = "",
    ) -> BenchmarkRecord:
        """Add a PipelineResult to the collector.

        Parameters
        ----------
        result:
            The output of a single pipeline run.
        source_file:
            Basename of the C source file (for identification).

        Returns
        -------
        BenchmarkRecord
            The created record.
        """
        record = BenchmarkRecord.from_pipeline_result(result, source_file=source_file)
        self.records.append(record)
        logger.info(
            "Recorded: %s — success=%s, confidence=%.2f, hallucinations=%d",
            source_file,
            record.success,
            record.final_confidence,
            record.total_hallucinations,
        )
        return record

    def add_from_report(
        self,
        report: AlignmentReport,
        source_file: str = "",
        model: str = "",
        attempts: int = 1,
        total_time_ms: float = 0.0,
    ) -> BenchmarkRecord:
        """Add a standalone AlignmentReport (no full PipelineResult needed).

        Useful for Phase 1-only or Phase 2-only verification runs
        where the full pipeline isn't used.
        """
        cat_counts: dict[str, int] = {}
        for h in report.hallucinations:
            key = h.category.value
            cat_counts[key] = cat_counts.get(key, 0) + 1

        record = BenchmarkRecord(
            source_file=source_file,
            model=model,
            success=report.is_aligned,
            attempts=attempts,
            final_confidence=report.confidence,
            total_hallucinations=len(report.hallucinations),
            structural_hallucinations=len(report.structural_hallucinations),
            semantic_hallucinations=len(report.semantic_hallucinations),
            tolerated_idioms=len(report.tolerated_idioms),
            total_time_ms=total_time_ms,
            hallucination_categories=cat_counts,
            # NEW — similarity metrics from the report
            tree_edit_distance=report.tree_edit_distance,
            tree_similarity=report.tree_similarity,
            data_flow_jaccard=getattr(report, 'data_flow_jaccard', None),
            control_dep_jaccard=getattr(report, 'control_dep_jaccard', None),
            tversky_index=getattr(report, 'tversky_index', None),
        )
        self.records.append(record)
        return record

    def summarize(self) -> ExperimentSummary:
        """Compute aggregate statistics across all recorded benchmarks.

        Returns
        -------
        ExperimentSummary
            Aggregate statistics for the paper's results table.
        """
        if not self.records:
            return ExperimentSummary()

        n = len(self.records)
        successes = sum(1 for r in self.records if r.success)
        total_hall = sum(r.total_hallucinations for r in self.records)

        # Aggregate hallucination categories
        all_cats: dict[str, int] = {}
        for r in self.records:
            for cat, count in r.hallucination_categories.items():
                all_cats[cat] = all_cats.get(cat, 0) + count

        return ExperimentSummary(
            total_programs=n,
            successful_translations=successes,
            total_hallucinations=total_hall,
            hallucinations_by_category=all_cats,
            avg_confidence=sum(r.final_confidence for r in self.records) / n,
            avg_attempts=sum(r.attempts for r in self.records) / n,
            avg_time_ms=sum(r.total_time_ms for r in self.records) / n,
            success_rate=successes / n,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Export methods
    # ─────────────────────────────────────────────────────────────────────────

    def export_json(self, path: Path) -> None:
        """Export all records + summary to a JSON file.

        The JSON structure is::

            {
                "experiment": "...",
                "summary": {...},
                "records": [...]
            }
        """
        summary = self.summarize()
        data: dict[str, Any] = {
            "experiment": self.experiment_name,
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "total_programs": summary.total_programs,
                "successful_translations": summary.successful_translations,
                "success_rate": round(summary.success_rate, 4),
                "total_hallucinations": summary.total_hallucinations,
                "hallucinations_by_category": summary.hallucinations_by_category,
                "avg_confidence": round(summary.avg_confidence, 4),
                "avg_attempts": round(summary.avg_attempts, 2),
                "avg_time_ms": round(summary.avg_time_ms, 2),
            },
            "records": [
                {
                    "source_file": r.source_file,
                    "model": r.model,
                    "success": r.success,
                    "attempts": r.attempts,
                    "final_confidence": round(r.final_confidence, 4),
                    "total_hallucinations": r.total_hallucinations,
                    "structural_hallucinations": r.structural_hallucinations,
                    "semantic_hallucinations": r.semantic_hallucinations,
                    "tolerated_idioms": r.tolerated_idioms,
                    "total_time_ms": round(r.total_time_ms, 2),
                    "hallucination_categories": r.hallucination_categories,
                    "timestamp": r.timestamp,
                    # NEW — similarity metrics
                    "tree_edit_distance": r.tree_edit_distance,
                    "tree_similarity": round(r.tree_similarity, 4) if r.tree_similarity is not None else None,
                    "data_flow_jaccard": round(r.data_flow_jaccard, 4) if r.data_flow_jaccard is not None else None,
                    "control_dep_jaccard": round(r.control_dep_jaccard, 4) if r.control_dep_jaccard is not None else None,
                    "tversky_index": round(r.tversky_index, 4) if r.tversky_index is not None else None,
                }
                for r in self.records
            ],
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        logger.info("Exported %d records to %s", len(self.records), path)

    def export_csv(self, path: Path) -> None:
        """Export all records to a CSV file.

        Columns: source_file, model, success, attempts, final_confidence,
        total_hallucinations, structural_hallucinations, semantic_hallucinations,
        tolerated_idioms, total_time_ms, <one column per category>, timestamp.
        """
        if not self.records:
            logger.warning("No records to export")
            return

        # Collect all unique categories across all records
        all_cats: set[str] = set()
        for r in self.records:
            all_cats.update(r.hallucination_categories.keys())
        sorted_cats = sorted(all_cats)

        # Build header
        base_fields = [
            "source_file",
            "model",
            "success",
            "attempts",
            "final_confidence",
            "total_hallucinations",
            "structural_hallucinations",
            "semantic_hallucinations",
            "tolerated_idioms",
            "total_time_ms",
        ]
        header = base_fields + [f"cat_{c}" for c in sorted_cats] + ["timestamp"]

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()

            for r in self.records:
                row: dict[str, Any] = {
                    "source_file": r.source_file,
                    "model": r.model,
                    "success": r.success,
                    "attempts": r.attempts,
                    "final_confidence": round(r.final_confidence, 4),
                    "total_hallucinations": r.total_hallucinations,
                    "structural_hallucinations": r.structural_hallucinations,
                    "semantic_hallucinations": r.semantic_hallucinations,
                    "tolerated_idioms": r.tolerated_idioms,
                    "total_time_ms": round(r.total_time_ms, 2),
                    "timestamp": r.timestamp,
                }
                for cat in sorted_cats:
                    row[f"cat_{cat}"] = r.hallucination_categories.get(cat, 0)
                writer.writerow(row)

        logger.info("Exported %d records to %s", len(self.records), path)

    def to_csv_string(self) -> str:
        """Return CSV data as a string (for inline display or testing)."""
        buf = StringIO()
        if not self.records:
            return ""

        all_cats: set[str] = set()
        for r in self.records:
            all_cats.update(r.hallucination_categories.keys())
        sorted_cats = sorted(all_cats)

        base_fields = [
            "source_file",
            "success",
            "attempts",
            "final_confidence",
            "total_hallucinations",
            "total_time_ms",
        ]
        header = base_fields + [f"cat_{c}" for c in sorted_cats]

        writer = csv.DictWriter(buf, fieldnames=header)
        writer.writeheader()

        for r in self.records:
            row: dict[str, Any] = {
                "source_file": r.source_file,
                "success": r.success,
                "attempts": r.attempts,
                "final_confidence": round(r.final_confidence, 4),
                "total_hallucinations": r.total_hallucinations,
                "total_time_ms": round(r.total_time_ms, 2),
            }
            for cat in sorted_cats:
                row[f"cat_{cat}"] = r.hallucination_categories.get(cat, 0)
            writer.writerow(row)

        return buf.getvalue()
