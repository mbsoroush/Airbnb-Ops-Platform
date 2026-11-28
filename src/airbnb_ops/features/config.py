"""Names, the column contract and the build configuration for the feature dataset.

The 26 model-input columns, their order and the forbidden fields are the contract shared with
the model training code and the serving API. They are written into the dataset metadata so
later steps can check themselves against it instead of keeping their own copy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

ENTITY_COLUMN = "listing_id"
TARGET_COLUMN = "high_demand_proxy"
DEFAULT_DATASET_VERSION = "v1"

PAST_WINDOW_DAYS = 90
RECENT_WINDOW_DAYS = 30
FUTURE_WINDOW_DAYS = 30
DEFAULT_LABEL_THRESHOLD = 0.30

AUDIT_COLUMNS: tuple[str, ...] = ("listing_id", "cutoff_date", "dataset_version")

MODEL_INPUT_COLUMNS: tuple[str, ...] = (
    "room_type",
    "property_type",
    "neighbourhood_name",
    "accommodates",
    "bedrooms",
    "beds",
    "bathrooms",
    "listing_price",
    "minimum_nights",
    "maximum_nights",
    "instant_bookable",
    "host_is_superhost",
    "host_listing_count",
    "total_reviews_before_cutoff",
    "unique_reviewers_before_cutoff",
    "avg_comment_len_before_cutoff",
    "max_comment_len_before_cutoff",
    "days_since_last_review",
    "available_days_last_90d",
    "available_rate_last_90d",
    "avg_minimum_nights_calendar_last_90d",
    "avg_maximum_nights_calendar_last_90d",
    "available_days_last_30d",
    "available_rate_last_30d",
    "avg_minimum_nights_calendar_last_30d",
    "avg_maximum_nights_calendar_last_30d",
)

LABEL_ONLY_COLUMNS: tuple[str, ...] = (
    "future_calendar_days_observed_30d",
    "future_available_days_30d",
    "future_available_rate_30d",
    "high_demand_proxy",
)

# How the model input columns are treated by the model pipeline. The pipeline implements
# exactly this, and it is written into the dataset metadata so that training and serving read
# the same contract.
CATEGORICAL_COLUMNS: tuple[str, ...] = ("room_type", "property_type", "neighbourhood_name")
BOOLEAN_COLUMNS: tuple[str, ...] = ("instant_bookable", "host_is_superhost")
# Heavy right tails (prices up to about 80,000 per night, review counts, night limits): log1p.
LOG1P_COLUMNS: tuple[str, ...] = (
    "listing_price",
    "minimum_nights",
    "maximum_nights",
    "host_listing_count",
    "total_reviews_before_cutoff",
    "unique_reviewers_before_cutoff",
    "avg_comment_len_before_cutoff",
    "max_comment_len_before_cutoff",
    "avg_minimum_nights_calendar_last_90d",
    "avg_maximum_nights_calendar_last_90d",
    "avg_minimum_nights_calendar_last_30d",
    "avg_maximum_nights_calendar_last_30d",
)
NUMERIC_COLUMNS: tuple[str, ...] = tuple(
    c for c in MODEL_INPUT_COLUMNS if c not in CATEGORICAL_COLUMNS + BOOLEAN_COLUMNS
)

PREPROCESSING_CONTRACT: dict = {
    "categorical_columns": list(CATEGORICAL_COLUMNS),
    "boolean_columns": list(BOOLEAN_COLUMNS),
    "numeric_columns": list(NUMERIC_COLUMNS),
    "log1p_columns": list(LOG1P_COLUMNS),
    "numeric": "median imputation with a missing-value indicator; log1p for the log1p columns; "
    "standard scaling",
    "boolean": "cast to 0/1; most frequent imputation",
    "categorical": "most frequent imputation; one-hot encoding with rare categories grouped",
    "constant_columns": (
        "Columns that are constant in the training data (for Munich, instant_bookable is empty "
        "in the source file and becomes constant False) are excluded from the model. They stay "
        "part of the request contract."
    ),
}

# The final table: audit fields, then model inputs, then label-window columns.
TABLE_COLUMNS: tuple[str, ...] = AUDIT_COLUMNS + MODEL_INPUT_COLUMNS + LABEL_ONLY_COLUMNS

# Fields a prediction request must never contain: audit, label-window and target columns,
# plus the pseudonymized keys. Accepting any of them would be leakage or identity linking.
FORBIDDEN_MODEL_INPUTS: tuple[str, ...] = AUDIT_COLUMNS + LABEL_ONLY_COLUMNS + (
    "host_key",
    "reviewer_key",
)

# Columns that must never appear in the feature table (identifiers, pseudonyms, raw text).
FORBIDDEN_TABLE_COLUMNS: tuple[str, ...] = (
    "host_id",
    "host_key",
    "host_pseudo_id",
    "host_name",
    "review_id",
    "reviewer_id",
    "reviewer_key",
    "reviewer_pseudo_id",
    "reviewer_name",
    "license",
    "bathrooms_text",
    "comments",
)

# Columns (besides the entity key) that are not model inputs and not part of the label window.
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class FeatureConfig:
    """How to build one dataset version.

    The column names encode the windows (`_90d`, `_30d`), so the window lengths are fixed:
    a different window needs a new column contract, not just a new version string.
    `cutoff_date=None` means: use the earliest valid cutoff, derived from the data.
    """

    dataset_version: str = DEFAULT_DATASET_VERSION
    cutoff_date: date | None = None
    cutoff_reason: str | None = None
    label_threshold: float = DEFAULT_LABEL_THRESHOLD
    past_window_days: int = PAST_WINDOW_DAYS
    recent_window_days: int = RECENT_WINDOW_DAYS
    future_window_days: int = FUTURE_WINDOW_DAYS

    def __post_init__(self) -> None:
        if not _VERSION_RE.match(self.dataset_version):
            raise ValueError(
                f"dataset_version {self.dataset_version!r} may only contain letters, digits, "
                "'_', '-' and '.' (it is used in file names)"
            )
        windows = (self.past_window_days, self.recent_window_days, self.future_window_days)
        if windows != (PAST_WINDOW_DAYS, RECENT_WINDOW_DAYS, FUTURE_WINDOW_DAYS):
            raise ValueError(
                "Window lengths are fixed at 90/30/30 days because the column names encode "
                "them; changing them needs a new column contract."
            )
        if not 0 < self.label_threshold < 1:
            raise ValueError("label_threshold must be between 0 and 1 (exclusive)")
