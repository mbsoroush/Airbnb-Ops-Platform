"""Load a city's Inside Airbnb files into the Postgres `core` schema."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..db import Database
from ..sqlfiles import load_sql
from .clean import (
    CALENDAR_COLUMNS,
    CALENDAR_USECOLS,
    LISTING_COLUMNS,
    LISTING_USECOLS,
    REVIEW_COLUMNS,
    REVIEW_USECOLS,
    clean_calendar,
    clean_listings,
    clean_reviews,
)


def find_file(raw_dir: Path, stem: str) -> Path:
    for suffix in (".csv.gz", ".csv"):
        candidate = raw_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Expected {stem}.csv.gz or {stem}.csv in {raw_dir}")


def schema_sql() -> str:
    return load_sql("00_core_schema.sql")


def load_city(
    db: Database,
    raw_dir: Path,
    salt: str,
    truncate: bool = True,
    chunksize: int = 500_000,
) -> dict[str, int]:
    """Clean and bulk-load listings, calendar and reviews. Returns row counts loaded."""
    raw_dir = Path(raw_dir)
    listings_path = find_file(raw_dir, "listings")
    calendar_path = find_file(raw_dir, "calendar")
    reviews_path = find_file(raw_dir, "reviews")

    db.execute_script(schema_sql())
    if truncate:
        db.execute_script("TRUNCATE core.review, core.calendar_day, core.listing")

    listings = clean_listings(pd.read_csv(listings_path, usecols=LISTING_USECOLS), salt)
    counts = {"listing": db.copy_frame(listings, "core.listing", LISTING_COLUMNS)}
    known_ids = set(listings["listing_id"])

    cal_rows = 0
    for chunk in pd.read_csv(calendar_path, usecols=CALENDAR_USECOLS, chunksize=chunksize):
        cleaned = clean_calendar(chunk)
        cleaned = cleaned[cleaned["listing_id"].isin(known_ids)]
        cal_rows += db.copy_frame(cleaned, "core.calendar_day", CALENDAR_COLUMNS)
    counts["calendar_day"] = cal_rows

    reviews = clean_reviews(pd.read_csv(reviews_path, usecols=REVIEW_USECOLS), salt)
    reviews = reviews[reviews["listing_id"].isin(known_ids)]
    counts["review"] = db.copy_frame(reviews, "core.review", REVIEW_COLUMNS)

    db.execute_script("ANALYZE core.listing; ANALYZE core.calendar_day; ANALYZE core.review")
    return counts
