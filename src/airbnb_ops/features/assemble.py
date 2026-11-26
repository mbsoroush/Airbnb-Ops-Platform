"""Join the feature groups and the label into one table (pure, no database)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import TABLE_COLUMNS, FeatureConfig
from .cutoff import CutoffPlan
from .static import clean_static_features

_REVIEW_COUNT_COLUMNS = ["total_reviews_before_cutoff", "unique_reviewers_before_cutoff"]
_REVIEW_FLOAT_COLUMNS = _REVIEW_COUNT_COLUMNS + [
    "avg_comment_len_before_cutoff",
    "max_comment_len_before_cutoff",
]


@dataclass(frozen=True)
class AssemblyResult:
    frame: pd.DataFrame
    rule_counts: dict[str, int]


def make_label(future_available_rate: pd.Series, threshold: float) -> pd.Series:
    """high_demand_proxy = 1 when the future available rate is at or below the threshold.

    This is a low-availability proxy: unavailable means booked OR blocked by the host.
    """
    return (future_available_rate <= threshold).astype("int64")


def _review_features(reviews: pd.DataFrame, plan: CutoffPlan) -> pd.DataFrame:
    out = reviews.copy()
    last = pd.to_datetime(out["last_review_date"])
    out["days_since_last_review"] = (pd.Timestamp(plan.cutoff_date) - last).dt.days.astype(
        "float64"
    )
    for col in _REVIEW_FLOAT_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out.drop(columns=["last_review_date"])


def assemble_features(
    static: pd.DataFrame,
    reviews: pd.DataFrame,
    calendar: pd.DataFrame,
    label: pd.DataFrame,
    plan: CutoffPlan,
    config: FeatureConfig,
) -> AssemblyResult:
    """One row per listing at the cutoff. Drops are sequential and every one is counted."""
    frame, counts = clean_static_features(static)

    rev = _review_features(reviews, plan)
    frame = frame.merge(rev, on="listing_id", how="left", validate="one_to_one")
    counts["listings_without_reviews"] = int(frame["total_reviews_before_cutoff"].isna().sum())
    for col in _REVIEW_COUNT_COLUMNS:
        frame[col] = frame[col].fillna(0.0)

    n = len(frame)
    frame = frame.merge(calendar, on="listing_id", how="inner", validate="one_to_one")
    counts["dropped_no_calendar_history"] = n - len(frame)
    n = len(frame)
    frame = frame[frame["calendar_days_observed_90d"] == config.past_window_days]
    counts["dropped_incomplete_history_window"] = n - len(frame)

    n = len(frame)
    frame = frame.merge(label, on="listing_id", how="inner", validate="one_to_one")
    counts["dropped_no_label_window"] = n - len(frame)
    n = len(frame)
    frame = frame[frame["future_calendar_days_observed_30d"] == config.future_window_days]
    counts["dropped_incomplete_label_window"] = n - len(frame)

    frame = frame.drop(columns=["calendar_days_observed_90d", "calendar_days_observed_30d"])
    for col in ("available_days_last_90d", "available_days_last_30d",
                "future_calendar_days_observed_30d", "future_available_days_30d"):
        frame[col] = frame[col].astype("int64")
    frame["high_demand_proxy"] = make_label(
        frame["future_available_rate_30d"], config.label_threshold
    )
    frame["cutoff_date"] = plan.cutoff_date.isoformat()
    frame["dataset_version"] = config.dataset_version

    frame = frame[list(TABLE_COLUMNS)].sort_values("listing_id").reset_index(drop=True)
    counts["rows_final"] = len(frame)
    return AssemblyResult(frame=frame, rule_counts=counts)
