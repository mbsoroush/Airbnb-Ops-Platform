import numpy as np
import pandas as pd

from airbnb_ops.ingest.clean import (
    CALENDAR_COLUMNS,
    CALENDAR_USECOLS,
    LISTING_COLUMNS,
    LISTING_USECOLS,
    REVIEW_COLUMNS,
    REVIEW_USECOLS,
    clean_calendar,
    clean_listings,
    clean_reviews,
    parse_price,
)

SALT = "test-salt"


def test_parse_price_handles_symbols_commas_and_junk():
    out = parse_price(pd.Series(["$1,250.00", "$65.73", None, "abc"]))
    assert out.iloc[0] == 1250.0
    assert out.iloc[1] == 65.73
    assert np.isnan(out.iloc[2]) and np.isnan(out.iloc[3])


def test_clean_listings(mini_city):
    raw = pd.read_csv(mini_city / "listings.csv", usecols=LISTING_USECOLS)
    out = clean_listings(raw, SALT)
    assert list(out.columns) == LISTING_COLUMNS
    assert out["listing_id"].is_unique
    assert out["price"].isna().sum() == 1
    assert out["price"].max() == 1250.0
    assert out["host_key"].nunique() == 12  # 20 listings, 12 distinct hosts
    assert not {"host_id", "host_name"} & set(out.columns)
    # same input and salt -> same keys; different salt -> different keys
    assert clean_listings(raw, SALT)["host_key"].equals(out["host_key"])
    assert not clean_listings(raw, "other")["host_key"].equals(out["host_key"])


def test_clean_calendar_converts_availability_to_bool(mini_city):
    raw = pd.read_csv(mini_city / "calendar.csv", usecols=CALENDAR_USECOLS)
    out = clean_calendar(raw)
    assert list(out.columns) == CALENDAR_COLUMNS
    assert out["available"].dtype == bool
    assert len(out) == len(raw) == 280
    assert out["date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()


def test_clean_reviews_dedupes_and_pseudonymizes(mini_city):
    raw = pd.read_csv(mini_city / "reviews.csv", usecols=REVIEW_USECOLS)
    assert len(raw) == 61
    out = clean_reviews(raw, SALT)
    assert list(out.columns) == REVIEW_COLUMNS
    assert len(out) == 60 and out["review_id"].is_unique
    assert not {"reviewer_id", "reviewer_name", "comments"} & set(out.columns)
    assert (out["reviewer_key"].str.len() == 16).all()
