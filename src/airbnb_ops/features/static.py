"""Static listing features: parsing and the missing-value rules (pure functions)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def parse_bathrooms(value) -> float:
    """Turn Airbnb's `bathrooms_text` into a number of bathrooms; unknown -> NaN.

    '1 bath' -> 1.0, '1.5 baths' -> 1.5, '2 shared baths' -> 2.0, 'Half-bath' -> 0.5,
    'Shared half-bath' -> 0.5. A count in front of 'half' counts half-baths ('2 half-baths'
    -> 1.0).
    """
    if value is None or value is pd.NA:
        return np.nan
    text = str(value).strip().lower()
    if not text or text == "nan":
        return np.nan
    match = _NUMBER.search(text)
    half = "half" in text
    if match:
        number = float(match.group())
        return number * 0.5 if half else number
    return 0.5 if half else np.nan


def to_bool_filled(series: pd.Series) -> tuple[pd.Series, int]:
    """Missing booleans become False. Returns the series and how many were filled."""
    as_bool = pd.array(series, dtype="boolean")
    missing = int(pd.isna(as_bool).sum())
    return pd.Series(as_bool, index=series.index).fillna(False).astype(bool), missing


def clean_static_features(static: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply the missing-value rules to the static listing table.

    Rules (each count is reported in the validation report):
      * `bathrooms` is parsed from `bathrooms_text`, which is then dropped.
      * missing `room_type` / `property_type` -> "unknown".
      * missing `instant_bookable` / `host_is_superhost` -> False. This is a modeling choice,
        not a fact: a missing flag is treated like "not set".
      * rows with missing `accommodates`, `minimum_nights` or `maximum_nights` are dropped.
      * `bedrooms`, `beds`, `bathrooms` and `listing_price` stay missing (the model pipeline
        imputes them and records that they were missing).
    """
    df = static.copy()
    if not df["listing_id"].is_unique:
        raise ValueError("static listing table must have one row per listing_id")
    counts: dict[str, int] = {"listings_in_core": len(df)}

    for col in ("accommodates", "bedrooms", "beds", "listing_price", "minimum_nights",
                "maximum_nights", "host_listing_count"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["bathrooms"] = df["bathrooms_text"].map(parse_bathrooms).astype("float64")
    df = df.drop(columns=["bathrooms_text"])

    for col in ("room_type", "property_type"):
        missing = df[col].isna() | (df[col].astype("string").str.strip() == "")
        counts[f"filled_{col}_unknown"] = int(missing.sum())
        df[col] = df[col].where(~missing, "unknown").astype(str)
    df["neighbourhood_name"] = df["neighbourhood_name"].astype(str)

    for col in ("instant_bookable", "host_is_superhost"):
        df[col], filled = to_bool_filled(df[col])
        counts[f"filled_{col}_false"] = filled

    for col in ("accommodates", "minimum_nights", "maximum_nights"):
        missing = df[col].isna()
        counts[f"dropped_missing_{col}"] = int(missing.sum())
        df = df[~missing]

    for col in ("accommodates", "minimum_nights", "maximum_nights", "host_listing_count"):
        df[col] = df[col].astype("int64")
    return df.reset_index(drop=True), counts
