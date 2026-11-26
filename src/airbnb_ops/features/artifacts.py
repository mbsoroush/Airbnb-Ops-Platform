"""Versioned outputs: file names, hashing, metadata and the version-immutability check."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

from .config import (
    AUDIT_COLUMNS,
    ENTITY_COLUMN,
    FORBIDDEN_MODEL_INPUTS,
    FORBIDDEN_TABLE_COLUMNS,
    LABEL_ONLY_COLUMNS,
    MODEL_INPUT_COLUMNS,
    TARGET_COLUMN,
    FeatureConfig,
)
from .cutoff import CutoffPlan

TARGET_DEFINITION = (
    "high_demand_proxy = 1 when future_available_rate_30d <= label_threshold. "
    "The rate is the share of days after the cutoff (30 day window) that the calendar marks "
    "as available. A day is unavailable when it is booked OR blocked by the host, so this is "
    "a low-availability proxy, not confirmed booking demand."
)

MISSING_VALUE_RULES = {
    "bathrooms": "parsed from bathrooms_text; unknown stays missing",
    "room_type, property_type": "missing -> 'unknown'",
    "instant_bookable, host_is_superhost": (
        "missing -> False (a modeling choice, not a fact: a missing flag is treated as not set)"
    ),
    "accommodates, minimum_nights, maximum_nights": "rows with a missing value are dropped",
    "bedrooms, beds, bathrooms, listing_price": (
        "kept missing; the model pipeline imputes them and adds a missing indicator"
    ),
    "total_reviews_before_cutoff, unique_reviewers_before_cutoff": (
        "listings without reviews -> 0"
    ),
    "avg/max_comment_len_before_cutoff, days_since_last_review": (
        "listings without reviews (or without comment text) stay missing"
    ),
    "calendar windows": (
        "listings without a full 90 day history window or a full 30 day label window are dropped"
    ),
}

UNUSABLE_COLUMN_RULE = (
    "Columns that are constant or more than 95% missing are dropped when they are not part of "
    "the column contract. Contract columns are never dropped because the serving API fixes "
    "them; they trigger a warning in the validation report instead."
)

LIMITATIONS = [
    "Inside Airbnb's calendar is a forward-looking snapshot: it starts at the scrape date, so "
    "the history window and the label window both describe the future as seen on that one "
    "day. The history features were not observed before the cutoff in a real-time sense, and "
    "this is not a true temporal split (that would need several snapshots).",
    "The label is a proxy: unavailable means booked or blocked by the host. Far-future dates "
    "and holiday periods contain many host blocks, so the label partly reflects host "
    "behaviour, not demand.",
    "Reviews end at the snapshot date, which is before any valid cutoff. The review features "
    "are therefore identical for every valid cutoff, and days_since_last_review differs "
    "between cutoffs only by a constant shift.",
    "Datasets built from different cutoffs contain the same listings, so they are not "
    "independent evidence for each other.",
]


def artifact_paths(out_dir: Path, version: str) -> dict[str, Path]:
    out_dir = Path(out_dir)
    base = f"listing_availability_features_{version}"
    return {
        "csv": out_dir / f"{base}.csv",
        "parquet": out_dir / f"{base}.parquet",
        "metadata": out_dir / f"{base}_metadata.json",
        "validation": out_dir / f"{base}_validation_report.json",
        "pii_audit": out_dir / f"pii_audit_{version}.csv",
    }


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pyarrow_available() -> bool:
    return importlib.util.find_spec("pyarrow") is not None


class VersionExistsError(RuntimeError):
    """A dataset version already exists with different content."""


def check_version_free(paths: dict[str, Path], new_csv_sha256: str, overwrite: bool) -> None:
    """A dataset version is immutable: rebuilding it must give the same content.

    If metadata for this version exists and recorded a different CSV hash, refuse unless
    overwrite is set. Rebuilding with identical content is fine.
    """
    meta_path = paths["metadata"]
    if overwrite or not meta_path.exists():
        return
    try:
        old = json.loads(meta_path.read_text(encoding="utf-8"))["files"]["csv"]["sha256"]
    except (KeyError, ValueError, TypeError):
        return
    if old != new_csv_sha256:
        raise VersionExistsError(
            f"{meta_path.name} already exists with different content. Use a new --version "
            "(or --overwrite if you really mean to replace it)."
        )


def file_info(path: Path) -> dict:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def build_metadata(
    config: FeatureConfig,
    plan: CutoffPlan,
    ranges: dict,
    rule_counts: dict,
    files: dict,
    parquet_written: bool,
    inspection: dict,
    dropped_unusable_columns: list[str],
) -> dict:
    return {
        "dataset_version": config.dataset_version,
        "entity_column": ENTITY_COLUMN,
        "target_column": TARGET_COLUMN,
        "target_definition": TARGET_DEFINITION,
        "label_threshold": config.label_threshold,
        "windows": {
            "history_days": config.past_window_days,
            "recent_days": config.recent_window_days,
            "label_days": config.future_window_days,
        },
        "cutoff": plan.as_dict(),
        "source": {
            "tables": ["core.listing", "core.calendar_day", "core.review"],
            **{k: (v.isoformat() if v is not None else None) for k, v in ranges.items()},
            "snapshot_date_proxy": ranges["calendar_min_date"].isoformat(),
            "calendar_price": inspection["calendar_price"],
            "inspection": inspection,
        },
        "model_input_columns": list(MODEL_INPUT_COLUMNS),
        "label_only_columns": list(LABEL_ONLY_COLUMNS),
        "audit_columns": list(AUDIT_COLUMNS),
        "forbidden_model_inputs": list(FORBIDDEN_MODEL_INPUTS),
        "forbidden_table_columns": list(FORBIDDEN_TABLE_COLUMNS),
        "row_counts": rule_counts,
        "missing_value_rules": MISSING_VALUE_RULES,
        "unusable_column_rule": UNUSABLE_COLUMN_RULE,
        "dropped_unusable_columns": dropped_unusable_columns,
        "limitations": LIMITATIONS,
        "files": files,
        "parquet_written": parquet_written,
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
