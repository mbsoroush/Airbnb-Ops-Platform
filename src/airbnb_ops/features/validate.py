"""Validation of the final feature table (pure). Returns a JSON-serializable report."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    AUDIT_COLUMNS,
    FORBIDDEN_TABLE_COLUMNS,
    LABEL_ONLY_COLUMNS,
    MODEL_INPUT_COLUMNS,
    TABLE_COLUMNS,
    TARGET_COLUMN,
    FeatureConfig,
)
from .cutoff import CutoffPlan

HIGH_MISSING_THRESHOLD = 0.95
_RATE_COLUMNS = ["available_rate_last_90d", "available_rate_last_30d", "future_available_rate_30d"]
_COUNT_COLUMNS = [
    "accommodates", "minimum_nights", "maximum_nights", "host_listing_count",
    "total_reviews_before_cutoff", "unique_reviewers_before_cutoff",
    "available_days_last_90d", "available_days_last_30d", "future_available_days_30d",
]


def find_unusable_columns(df: pd.DataFrame, columns: list[str] | None = None) -> list[str]:
    """Columns that are constant or more than 95% missing (no signal)."""
    if not len(df):
        return []
    candidates = [c for c in (columns if columns is not None else df.columns) if c in df.columns]
    return [
        c for c in candidates
        if df[c].isna().mean() > HIGH_MISSING_THRESHOLD or df[c].nunique(dropna=True) <= 1
    ]


def drop_unusable_columns(
    df: pd.DataFrame, protected: tuple[str, ...] = TABLE_COLUMNS
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Drop unusable columns that are not part of the contract.

    Contract columns are never dropped (the API contract is fixed); they are returned as the
    third value so the caller can warn about them. Returns (frame, dropped, kept_in_contract).
    """
    unusable = find_unusable_columns(df)
    dropped = [c for c in unusable if c not in protected]
    kept = [c for c in unusable if c in protected]
    return df.drop(columns=dropped), dropped, kept


class FeatureValidationError(ValueError):
    """Raised when the feature table fails a mandatory check."""


def _py(value: Any) -> Any:
    """numpy/pandas scalars -> plain JSON-friendly values (NaN -> None)."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def validate_feature_frame(df: pd.DataFrame, plan: CutoffPlan, config: FeatureConfig) -> dict:
    """Run every mandatory check and collect the statistics that go into the report."""
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    def check(name: str, ok: bool, message: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            errors.append(message)

    check("has_rows", len(df) > 0, "the feature table has no rows")
    check(
        "column_contract",
        list(df.columns) == list(TABLE_COLUMNS),
        "columns differ from the contract (names or order)",
    )

    duplicates = int(df.duplicated(subset=["listing_id", "cutoff_date"]).sum())
    check("no_duplicate_listing_cutoff", duplicates == 0, f"{duplicates} duplicate listing rows")

    present_forbidden = sorted(set(FORBIDDEN_TABLE_COLUMNS) & set(df.columns))
    check("no_forbidden_columns", not present_forbidden, f"forbidden columns: {present_forbidden}")

    model_inputs = [
        c for c in df.columns if c not in LABEL_ONLY_COLUMNS and c not in AUDIT_COLUMNS
    ]
    leakage = [c for c in model_inputs if c.startswith("future_") or c == TARGET_COLUMN]
    check("no_future_leakage_in_model_inputs", not leakage, f"future columns in inputs: {leakage}")
    check(
        "model_inputs_match_contract",
        model_inputs == list(MODEL_INPUT_COLUMNS),
        "model input columns differ from the contract",
    )

    missing_target = int(df[TARGET_COLUMN].isna().sum()) if TARGET_COLUMN in df else len(df)
    target_values = sorted(df[TARGET_COLUMN].dropna().unique().tolist()) if len(df) else []
    check("target_not_missing", missing_target == 0, f"{missing_target} missing target values")
    check("target_is_binary", set(target_values) <= {0, 1}, f"target values {target_values}")
    check("both_classes_present", set(target_values) == {0, 1}, "target has only one class")

    if len(df) and not errors:
        observed = df["future_calendar_days_observed_30d"]
        check(
            "label_window_complete",
            bool((observed == config.future_window_days).all()),
            "some rows have an incomplete label window",
        )
        rate_from_days = df["future_available_days_30d"] / observed
        check(
            "future_rate_consistent",
            bool(np.allclose(rate_from_days, df["future_available_rate_30d"])),
            "future_available_rate_30d does not match days / observed",
        )
        expected = (df["future_available_rate_30d"] <= config.label_threshold).astype(int)
        check(
            "label_matches_rule",
            bool((expected == df[TARGET_COLUMN]).all()),
            f"{TARGET_COLUMN} does not follow the threshold rule",
        )
        check(
            "rates_in_unit_interval",
            all(bool(df[c].between(0, 1).all()) for c in _RATE_COLUMNS),
            "a rate column is outside [0, 1]",
        )
        check(
            "counts_non_negative",
            all(bool((df[c] >= 0).all()) for c in _COUNT_COLUMNS),
            "a count column has negative values",
        )
        check(
            "window_counts_within_window",
            bool(
                (df["available_days_last_90d"] <= config.past_window_days).all()
                and (df["available_days_last_30d"] <= config.recent_window_days).all()
                and (df["available_days_last_30d"] <= df["available_days_last_90d"]).all()
            ),
            "available day counts exceed their window",
        )
        days_since = df["days_since_last_review"].dropna()
        check("days_since_review_non_negative", bool((days_since >= 0).all()),
              "days_since_last_review is negative for some rows")
        check(
            "cutoff_and_version_constant",
            bool(
                (df["cutoff_date"] == plan.cutoff_date.isoformat()).all()
                and (df["dataset_version"] == config.dataset_version).all()
            ),
            "cutoff_date or dataset_version differs from the build configuration",
        )

    unusable = find_unusable_columns(df, list(MODEL_INPUT_COLUMNS))
    if unusable:
        warnings.append(
            f"WARNING: contract columns {unusable} are constant or more than 95% missing, so "
            "they carry no signal. They are kept only because the column contract is fixed."
        )

    missing_report = [
        {"column": c, "missing_rate": round(float(r), 4)}
        for c, r in df.isna().mean().sort_values(ascending=False).items()
    ]
    distribution: list[dict] = []
    if TARGET_COLUMN in df and len(df):
        counts = df[TARGET_COLUMN].value_counts(dropna=False).sort_index()
        for value, count in counts.items():
            distribution.append(
                {
                    TARGET_COLUMN: _py(value),
                    "count": int(count),
                    "percentage": round(float(count) / len(df), 4),
                }
            )
    coverage = {}
    if "future_calendar_days_observed_30d" in df and len(df):
        described = df["future_calendar_days_observed_30d"].describe()
        coverage = {str(k): _py(float(v)) for k, v in described.items()}
    price_summary = {}
    if "listing_price" in df and len(df):
        price = df["listing_price"]
        quantiles = price.quantile([0.01, 0.5, 0.99, 0.999])
        price_summary = {
            "missing_rate": round(float(price.isna().mean()), 4),
            "quantiles": {str(q): _py(float(v)) for q, v in quantiles.items()},
            "max": _py(float(price.max())) if price.notna().any() else None,
        }

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "n_rows": len(df),
        "duplicate_listing_cutoff_rows": duplicates,
        "missing_target_count": missing_target,
        "target_values": [_py(v) for v in target_values],
        "present_forbidden_columns": present_forbidden,
        "future_leakage_columns_in_model_inputs": leakage,
        "model_input_column_count": len(model_inputs),
        "unusable_contract_columns": unusable,
        "missing_report": missing_report,
        "label_distribution": distribution,
        "calendar_coverage_summary": coverage,
        "listing_price_summary": price_summary,
    }


def assert_valid(report: dict) -> None:
    if not report["passed"]:
        raise FeatureValidationError("; ".join(report["errors"]))
