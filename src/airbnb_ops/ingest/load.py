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
    LISTING_OPTIONAL_USECOLS,
    LISTING_REQUIRED_USECOLS,
    REVIEW_COLUMNS,
    REVIEW_OPTIONAL_USECOLS,
    REVIEW_REQUIRED_USECOLS,
    clean_calendar,
    clean_listings,
    clean_reviews,
    select_usecols,
)


def find_file(raw_dir: Path, stem: str) -> Path:
    for suffix in (".csv.gz", ".csv"):
        candidate = raw_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Expected {stem}.csv.gz or {stem}.csv in {raw_dir}")


def schema_sql() -> str:
    """Base tables, then the additive migration (see 04_core_ml_columns.sql)."""
    return load_sql("00_core_schema.sql") + "\n" + load_sql("04_core_ml_columns.sql")


def load_city(
    db: Database,
    raw_dir: Path,
    salt: str,
    truncate: bool = True,
    chunksize: int = 500_000,
    review_chunksize: int = 100_000,
) -> dict[str, int]:
    """Clean and bulk-load listings, calendar and reviews. Returns row counts loaded."""
    raw_dir = Path(raw_dir)
    listings_path = find_file(raw_dir, "listings")
    calendar_path = find_file(raw_dir, "calendar")
    reviews_path = find_file(raw_dir, "reviews")

    db.execute_script(schema_sql())
    if truncate:
        db.execute_script("TRUNCATE core.review, core.calendar_day, core.listing")

    listing_cols = select_usecols(listings_path, LISTING_REQUIRED_USECOLS, LISTING_OPTIONAL_USECOLS)
    listings = clean_listings(pd.read_csv(listings_path, usecols=listing_cols), salt)
    counts = {"listing": db.copy_frame(listings, "core.listing", LISTING_COLUMNS)}
    known_ids = set(listings["listing_id"])

    cal_rows = 0
    for chunk in pd.read_csv(calendar_path, usecols=CALENDAR_USECOLS, chunksize=chunksize):
        cleaned = clean_calendar(chunk)
        cleaned = cleaned[cleaned["listing_id"].isin(known_ids)]
        cal_rows += db.copy_frame(cleaned, "core.calendar_day", CALENDAR_COLUMNS)
    counts["calendar_day"] = cal_rows

    # Reviews are read in chunks because the comments column is large. Review ids are
    # de-duplicated across chunks with a set of ids already loaded.
    review_cols = select_usecols(reviews_path, REVIEW_REQUIRED_USECOLS, REVIEW_OPTIONAL_USECOLS)
    seen_review_ids: set[int] = set()
    review_rows = 0
    for chunk in pd.read_csv(reviews_path, usecols=review_cols, chunksize=review_chunksize):
        cleaned = clean_reviews(chunk, salt)
        cleaned = cleaned[cleaned["listing_id"].isin(known_ids)]
        cleaned = cleaned[~cleaned["review_id"].isin(seen_review_ids)]
        seen_review_ids.update(cleaned["review_id"])
        review_rows += db.copy_frame(cleaned, "core.review", REVIEW_COLUMNS)
    counts["review"] = review_rows

    db.execute_script("ANALYZE core.listing; ANALYZE core.calendar_day; ANALYZE core.review")
    return counts
