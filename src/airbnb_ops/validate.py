"""Output validation. Raises ValueError on any failed check."""
import pandas as pd

from .transform import OUTPUT_COLUMNS

PII_COLUMNS = [
    "host_name", "host_id", "host_key",
    "reviewer_name", "reviewer_id", "listing_url", "host_url",
]


def validate_summary(summary: pd.DataFrame) -> None:
    if summary is None or summary.empty:
        raise ValueError("Summary is empty.")

    missing = [c for c in OUTPUT_COLUMNS if c not in summary.columns]
    if missing:
        raise ValueError(f"Summary missing required columns: {missing}")

    leaked = [c for c in PII_COLUMNS if c in summary.columns]
    if leaked:
        raise ValueError(f"PII columns present in summary: {leaked}")

    if summary["neighbourhood"].isna().any():
        raise ValueError("neighbourhood contains null values.")
    if not (summary["num_listings"] > 0).all():
        raise ValueError("num_listings must be > 0 for every row.")
    if not (summary["avg_price"] >= 0).all():
        raise ValueError("avg_price must be >= 0.")
    if not summary["availability_365_avg"].between(0, 365).all():
        raise ValueError("availability_365_avg must be between 0 and 365.")
