"""Build the versioned feature dataset: orchestration only, logic lives in the pure modules."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from ..sqlfiles import load_sql
from .artifacts import (
    artifact_paths,
    build_metadata,
    check_version_free,
    csv_bytes,
    file_info,
    pyarrow_available,
    sha256_bytes,
    write_json,
)
from .assemble import assemble_features
from .audit import build_pii_audit
from .config import FeatureConfig
from .cutoff import CutoffPlan, plan_cutoff
from .report import render_markdown
from .source_inspection import inspect_source
from .validate import assert_valid, drop_unusable_columns, validate_feature_frame


class FrameReader(Protocol):
    """Anything that can run a SQL file with bound parameters and return a DataFrame."""

    def read_frame(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame: ...


@dataclass(frozen=True)
class BuildResult:
    frame: pd.DataFrame
    plan: CutoffPlan
    report: dict
    metadata: dict
    rule_counts: dict
    paths: dict[str, Path]


def _to_date(value) -> date | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date()


def read_source_ranges(reader: FrameReader) -> dict[str, date | None]:
    row = reader.read_frame(load_sql("10_source_ranges.sql")).iloc[0]
    ranges = {k: _to_date(row[k]) for k in (
        "calendar_min_date", "calendar_max_date", "review_min_date", "review_max_date"
    )}
    if ranges["calendar_min_date"] is None or ranges["calendar_max_date"] is None:
        raise ValueError("core.calendar_day is empty: run `airbnb-ops ingest` first")
    return ranges


def build_feature_frame(reader: FrameReader, config: FeatureConfig):
    """Read, aggregate (in SQL) and assemble. No files are written here."""
    ranges = read_source_ranges(reader)
    plan = plan_cutoff(ranges["calendar_min_date"], ranges["calendar_max_date"], config)

    static = reader.read_frame(load_sql("11_feature_static_listing.sql"))
    reviews = reader.read_frame(
        load_sql("12_feature_reviews.sql"), {"cutoff_date": plan.cutoff_date}
    )
    calendar = reader.read_frame(
        load_sql("13_feature_calendar.sql"),
        {
            "history_start_date": plan.history_start_date,
            "recent_start_date": plan.recent_start_date,
            "cutoff_date": plan.cutoff_date,
        },
    )
    label = reader.read_frame(
        load_sql("14_label_window.sql"),
        {"cutoff_date": plan.cutoff_date, "label_end_date": plan.label_end_date},
    )

    result = assemble_features(static, reviews, calendar, label, plan, config)
    frame, dropped, _ = drop_unusable_columns(result.frame)
    result = replace(
        result,
        frame=frame,
        rule_counts={**result.rule_counts, "dropped_unusable_columns": len(dropped)},
    )
    report = validate_feature_frame(result.frame, plan, config)
    report["dropped_unusable_columns"] = dropped
    return result, plan, ranges, report


def build_feature_dataset(
    reader: FrameReader,
    config: FeatureConfig,
    out_dir: Path,
    overwrite: bool = False,
    reports_dir: Path | None = None,
) -> BuildResult:
    """Build, validate and save one dataset version. Nothing is written if validation fails."""
    inspection = inspect_source(reader)
    result, plan, ranges, report = build_feature_frame(reader, config)
    assert_valid(report)

    paths = artifact_paths(out_dir, config.dataset_version)
    data = csv_bytes(result.frame)
    check_version_free(paths, sha256_bytes(data), overwrite)

    paths["csv"].parent.mkdir(parents=True, exist_ok=True)
    paths["csv"].write_bytes(data)
    parquet_written = pyarrow_available()
    if parquet_written:
        result.frame.to_parquet(paths["parquet"], index=False)
    files = {
        "csv": file_info(paths["csv"]),
        "parquet": file_info(paths["parquet"]) if parquet_written else None,
    }

    metadata = build_metadata(
        config, plan, ranges, result.rule_counts, files, parquet_written, inspection,
        report["dropped_unusable_columns"],
    )
    write_json(paths["metadata"], metadata)
    write_json(paths["validation"], report)
    build_pii_audit().to_csv(paths["pii_audit"], index=False)

    if reports_dir is not None:
        reports_dir = Path(reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"features_{config.dataset_version}.md").write_text(
            render_markdown(metadata, report), encoding="utf-8"
        )
    return BuildResult(result.frame, plan, report, metadata, result.rule_counts, paths)
