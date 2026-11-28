"""Synthetic feature tables with the real column contract, for the ML tests (no database)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from airbnb_ops.features.config import TABLE_COLUMNS
from airbnb_ops.ml.data import LoadedDataset

NEIGHBOURHOODS = [f"Quarter {i}" for i in range(12)]
PROPERTY_TYPES = ["Entire rental unit"] * 5 + ["Private room in rental unit"] * 3 + [
    "Entire condo", "Room in hotel", "Tiny house"]


def make_feature_frame(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rate90 = np.clip(rng.beta(2, 2, n), 0, 1)
    days90 = np.round(rate90 * 90).astype(int)
    rate90 = days90 / 90
    rate30 = np.clip(rate90 + rng.normal(0, 0.15, n), 0, 1)
    days30 = np.round(rate30 * 30).astype(int)
    rate30 = days30 / 30
    future = np.clip(0.75 * rate30 + 0.25 * rng.random(n) + rng.normal(0, 0.05, n), 0, 1)
    future_days = np.round(future * 30).astype(int)
    future_rate = future_days / 30

    price = np.exp(rng.normal(5.2, 0.6, n))
    price[rng.random(n) < 0.32] = np.nan
    price[3] = 79599.92
    reviews = rng.poisson(12, n).astype(float)
    reviews[rng.random(n) < 0.2] = 0.0
    has_reviews = reviews > 0
    comment_avg = np.where(has_reviews, rng.normal(180, 40, n), np.nan)
    comment_max = np.where(has_reviews, comment_avg + rng.integers(50, 400, n), np.nan)
    since = np.where(has_reviews, 90 + rng.integers(0, 900, n), np.nan)

    frame = pd.DataFrame(
        {
            "listing_id": np.arange(1, n + 1),
            "cutoff_date": "2026-12-24",
            "dataset_version": "v1",
            "room_type": rng.choice(["Entire home/apt", "Private room", "Hotel room"], n,
                                    p=[0.6, 0.35, 0.05]),
            "property_type": rng.choice(PROPERTY_TYPES, n),
            "neighbourhood_name": rng.choice(NEIGHBOURHOODS, n),
            "accommodates": rng.integers(1, 9, n),
            "bedrooms": np.where(rng.random(n) < 0.05, np.nan, rng.integers(1, 4, n).astype(float)),
            "beds": rng.integers(1, 6, n).astype(float),
            "bathrooms": np.where(rng.random(n) < 0.03, np.nan, rng.choice([1.0, 1.5, 2.0], n)),
            "listing_price": price,
            "minimum_nights": rng.integers(1, 30, n),
            "maximum_nights": rng.choice([30, 365, 1125, 99999], n),
            "instant_bookable": False,
            "host_is_superhost": rng.random(n) < 0.3,
            "host_listing_count": rng.integers(1, 20, n),
            "total_reviews_before_cutoff": reviews,
            "unique_reviewers_before_cutoff": np.floor(reviews * 0.9),
            "avg_comment_len_before_cutoff": comment_avg,
            "max_comment_len_before_cutoff": comment_max,
            "days_since_last_review": since,
            "available_days_last_90d": days90,
            "available_rate_last_90d": rate90,
            "avg_minimum_nights_calendar_last_90d": rng.uniform(1, 30, n),
            "avg_maximum_nights_calendar_last_90d": rng.uniform(30, 1125, n),
            "available_days_last_30d": days30,
            "available_rate_last_30d": rate30,
            "avg_minimum_nights_calendar_last_30d": rng.uniform(1, 30, n),
            "avg_maximum_nights_calendar_last_30d": rng.uniform(30, 1125, n),
            "future_calendar_days_observed_30d": 30,
            "future_available_days_30d": future_days,
            "future_available_rate_30d": future_rate,
        }
    )
    frame["high_demand_proxy"] = (frame["future_available_rate_30d"] <= 0.30).astype(int)
    return frame[list(TABLE_COLUMNS)]


def make_host_groups(frame: pd.DataFrame, seed: int = 1, n_hosts: int = 150) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.integers(0, n_hosts, len(frame)), index=frame["listing_id"].to_numpy())


def make_loaded_dataset(frame: pd.DataFrame | None = None, version: str = "v1") -> LoadedDataset:
    frame = make_feature_frame() if frame is None else frame
    metadata = {
        "dataset_version": version,
        "cutoff": {"cutoff_date": "2026-12-24"},
        "label_threshold": 0.3,
        "files": {"csv": {"sha256": "c" * 64}, "parquet": None},
        "model_input_columns": list(TABLE_COLUMNS[3:29]),
    }
    return LoadedDataset(
        frame=frame, metadata=metadata, version=version, source_file=f"fake_{version}.csv",
        sha256="a" * 64, csv_sha256="c" * 64,
    )
