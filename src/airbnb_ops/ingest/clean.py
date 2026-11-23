"""Pure cleaning functions for Inside Airbnb files (no database needed).

Only the columns we need are ever read: free-text and name columns
(host_name, reviewer_name, comments, descriptions) never enter memory.
"""
from __future__ import annotations

import pandas as pd

from ..pii import pseudonymize_value

LISTING_USECOLS = [
    "id", "neighbourhood_cleansed", "room_type", "property_type", "accommodates", "price",
    "minimum_nights", "availability_30", "availability_365", "number_of_reviews",
    "review_scores_rating", "host_id", "latitude", "longitude",
]
CALENDAR_USECOLS = ["listing_id", "date", "available", "minimum_nights", "maximum_nights"]
REVIEW_USECOLS = ["listing_id", "id", "date", "reviewer_id"]

LISTING_COLUMNS = [
    "listing_id", "neighbourhood", "room_type", "property_type", "accommodates", "price",
    "minimum_nights", "availability_30", "availability_365", "number_of_reviews",
    "review_scores_rating", "host_key", "latitude", "longitude",
]
CALENDAR_COLUMNS = ["listing_id", "date", "available", "minimum_nights", "maximum_nights"]
REVIEW_COLUMNS = ["review_id", "listing_id", "review_date", "reviewer_key"]

_INT_LISTING_COLS = [
    "accommodates", "minimum_nights", "availability_30", "availability_365", "number_of_reviews",
]


def parse_price(series: pd.Series) -> pd.Series:
    """'$1,250.00' -> 1250.0 ; missing or unparseable -> NaN."""
    cleaned = series.astype("string").str.replace(r"[$,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def _pseudonymize(series: pd.Series, salt: str) -> pd.Series:
    mapping = {v: pseudonymize_value(v, salt) for v in series.dropna().unique()}
    return series.map(mapping)


def clean_listings(raw: pd.DataFrame, salt: str) -> pd.DataFrame:
    df = raw.rename(columns={"id": "listing_id", "neighbourhood_cleansed": "neighbourhood"})
    df = df.dropna(subset=["listing_id", "neighbourhood", "host_id"]).copy()
    df = df.drop_duplicates(subset="listing_id")
    df["listing_id"] = df["listing_id"].astype("int64")
    df["price"] = parse_price(df["price"])
    for col in _INT_LISTING_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
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
    """Drop duplicate review ids and replace reviewer_id with a stable pseudonym."""
    df = raw.rename(columns={"id": "review_id", "date": "review_date"})
    df = df.dropna(subset=["review_id", "listing_id", "review_date", "reviewer_id"]).copy()
    df = df.drop_duplicates(subset="review_id")
    df["review_id"] = df["review_id"].astype("int64")
    df["listing_id"] = df["listing_id"].astype("int64")
    df["review_date"] = pd.to_datetime(df["review_date"]).dt.strftime("%Y-%m-%d")
    df["reviewer_key"] = _pseudonymize(df["reviewer_id"], salt)
    return df[REVIEW_COLUMNS].reset_index(drop=True)
