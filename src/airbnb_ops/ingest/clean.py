"""Pure cleaning functions for Inside Airbnb files (no database needed).

Only the columns we need are ever read: name columns (host_name, reviewer_name) and
descriptions never enter memory. The one exception is the review `comments` column, which is
read only to compute `comment_len` (an integer) and is dropped immediately afterwards.

Columns added for the feature dataset are optional: a file without them (such as the small
test fixtures) still loads, with NULL in those columns.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..pii import pseudonymize_value

LISTING_REQUIRED_USECOLS = [
    "id", "neighbourhood_cleansed", "room_type", "property_type", "accommodates", "price",
    "minimum_nights", "availability_30", "availability_365", "number_of_reviews",
    "review_scores_rating", "host_id", "latitude", "longitude",
]
LISTING_OPTIONAL_USECOLS = [
    "bedrooms", "beds", "bathrooms_text", "maximum_nights", "instant_bookable",
    "host_is_superhost",
]
CALENDAR_USECOLS = ["listing_id", "date", "available", "minimum_nights", "maximum_nights"]
REVIEW_REQUIRED_USECOLS = ["listing_id", "id", "date", "reviewer_id"]
REVIEW_OPTIONAL_USECOLS = ["comments"]

# Backwards compatible names: the columns every input file must have. Optional columns are
# added per file by `select_usecols`.
LISTING_USECOLS = LISTING_REQUIRED_USECOLS
REVIEW_USECOLS = REVIEW_REQUIRED_USECOLS

LISTING_COLUMNS = [
    "listing_id", "neighbourhood", "room_type", "property_type", "accommodates", "price",
    "minimum_nights", "availability_30", "availability_365", "number_of_reviews",
    "review_scores_rating", "host_key", "latitude", "longitude",
    "bedrooms", "beds", "bathrooms_text", "maximum_nights", "instant_bookable",
    "host_is_superhost",
]
CALENDAR_COLUMNS = ["listing_id", "date", "available", "minimum_nights", "maximum_nights"]
REVIEW_COLUMNS = ["review_id", "listing_id", "review_date", "reviewer_key", "comment_len"]

_INT_LISTING_COLS = [
    "accommodates", "minimum_nights", "availability_30", "availability_365", "number_of_reviews",
    "maximum_nights",
]
_FLOAT_LISTING_COLS = ["bedrooms", "beds"]
_BOOL_LISTING_COLS = ["instant_bookable", "host_is_superhost"]


def select_usecols(path: Path, required: list[str], optional: list[str]) -> list[str]:
    """Columns to read from a CSV: all required ones, plus the optional ones the file has.

    Raises a clear error when a required column is missing.
    """
    header = list(pd.read_csv(path, nrows=0).columns)
    missing = [c for c in required if c not in header]
    if missing:
        raise ValueError(f"{Path(path).name} is missing required columns: {missing}")
    return required + [c for c in optional if c in header]


def parse_price(series: pd.Series) -> pd.Series:
    """'$1,250.00' -> 1250.0 ; missing or unparseable -> NaN."""
    cleaned = series.astype("string").str.replace(r"[$,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def parse_tf(series: pd.Series) -> pd.Series:
    """Inside Airbnb booleans: 't' -> True, 'f' -> False, anything else -> missing."""
    return series.astype("string").str.strip().str.lower().map({"t": True, "f": False}).astype(
        "boolean"
    )


def _pseudonymize(series: pd.Series, salt: str) -> pd.Series:
    mapping = {v: pseudonymize_value(v, salt) for v in series.dropna().unique()}
    return series.map(mapping)


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Add all-missing columns for optional columns that the source file does not have."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = pd.NA
    return out


def clean_listings(raw: pd.DataFrame, salt: str) -> pd.DataFrame:
    df = _ensure_columns(raw, LISTING_OPTIONAL_USECOLS)
    df = df.rename(columns={"id": "listing_id", "neighbourhood_cleansed": "neighbourhood"})
    df = df.dropna(subset=["listing_id", "neighbourhood", "host_id"]).copy()
    df = df.drop_duplicates(subset="listing_id")
    df["listing_id"] = df["listing_id"].astype("int64")
    df["price"] = parse_price(df["price"])
    for col in _INT_LISTING_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in _FLOAT_LISTING_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    for col in _BOOL_LISTING_COLS:
        df[col] = parse_tf(df[col])
    df["bathrooms_text"] = df["bathrooms_text"].astype("string").str.strip()
    df["host_key"] = _pseudonymize(df["host_id"], salt)
    return df[LISTING_COLUMNS].reset_index(drop=True)


def clean_calendar(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["available"] = df["available"].map({"t": True, "f": False})
    df = df.dropna(subset=["listing_id", "date", "available"])
    df["listing_id"] = df["listing_id"].astype("int64")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in ("minimum_nights", "maximum_nights"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df[CALENDAR_COLUMNS].reset_index(drop=True)


def clean_reviews(raw: pd.DataFrame, salt: str) -> pd.DataFrame:
    """Drop duplicate review ids, pseudonymize reviewer_id, keep only the comment length.

    `comment_len` is NULL when the file has no comments column or the comment is missing.
    The comment text itself is never part of the output.
    """
    df = _ensure_columns(raw, REVIEW_OPTIONAL_USECOLS)
    df = df.rename(columns={"id": "review_id", "date": "review_date"})
    df = df.dropna(subset=["review_id", "listing_id", "review_date", "reviewer_id"]).copy()
    df = df.drop_duplicates(subset="review_id")
    df["review_id"] = df["review_id"].astype("int64")
    df["listing_id"] = df["listing_id"].astype("int64")
    df["review_date"] = pd.to_datetime(df["review_date"]).dt.strftime("%Y-%m-%d")
    df["reviewer_key"] = _pseudonymize(df["reviewer_id"], salt)
    df["comment_len"] = df["comments"].astype("string").str.len().astype("Int64")
    return df[REVIEW_COLUMNS].reset_index(drop=True)
