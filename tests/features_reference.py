"""Independent pandas implementation of the feature SQL, used by tests only.

`FakeReader` answers the same `read_frame(sql, params)` calls as the database, but computes the
results with pandas from a fixture folder. Unit tests use it to run the whole builder without
Postgres; the Postgres integration test compares the real SQL against it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from airbnb_ops.ingest.clean import (
    CALENDAR_USECOLS,
    LISTING_OPTIONAL_USECOLS,
    LISTING_REQUIRED_USECOLS,
    REVIEW_OPTIONAL_USECOLS,
    REVIEW_REQUIRED_USECOLS,
    clean_calendar,
    clean_listings,
    clean_reviews,
    select_usecols,
)
from airbnb_ops.sqlfiles import load_sql

SALT = "test-salt"


def load_core_frames(fixture_dir: Path) -> dict[str, pd.DataFrame]:
    """Clean a fixture folder exactly like ingest does (without a database)."""
    fixture_dir = Path(fixture_dir)
    lp, cp, rp = (fixture_dir / f"{n}.csv" for n in ("listings", "calendar", "reviews"))
    cols = select_usecols(lp, LISTING_REQUIRED_USECOLS, LISTING_OPTIONAL_USECOLS)
    listing = clean_listings(pd.read_csv(lp, usecols=cols), SALT)
    calendar = clean_calendar(pd.read_csv(cp, usecols=CALENDAR_USECOLS))
    rcols = select_usecols(rp, REVIEW_REQUIRED_USECOLS, REVIEW_OPTIONAL_USECOLS)
    review = clean_reviews(pd.read_csv(rp, usecols=rcols), SALT)
    return {"listing": listing, "calendar": calendar, "review": review}


def _iso(value) -> str:
    return pd.Timestamp(value).date().isoformat()


class FakeReader:
    def __init__(self, core: dict[str, pd.DataFrame]):
        self.core = core
        self.calls: list[tuple[str, dict | None]] = []
        self._sql = {
            "ranges": load_sql("10_source_ranges.sql"),
            "static": load_sql("11_feature_static_listing.sql"),
            "reviews": load_sql("12_feature_reviews.sql"),
            "calendar": load_sql("13_feature_calendar.sql"),
            "label": load_sql("14_label_window.sql"),
            "inspection": load_sql("15_source_inspection.sql"),
            "columns": load_sql("16_core_columns.sql"),
        }

    def read_frame(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        name = next(k for k, v in self._sql.items() if v == sql)
        self.calls.append((name, params))
        return getattr(self, f"_{name}")(params)

    def _ranges(self, params):
        cal, rev = self.core["calendar"], self.core["review"]
        return pd.DataFrame(
            [{
                "calendar_min_date": pd.Timestamp(cal["date"].min()),
                "calendar_max_date": pd.Timestamp(cal["date"].max()),
                "review_min_date": pd.Timestamp(rev["review_date"].min()),
                "review_max_date": pd.Timestamp(rev["review_date"].max()),
            }]
        )

    def _inspection(self, params):
        listing, cal, rev = self.core["listing"], self.core["calendar"], self.core["review"]
        return pd.DataFrame(
            [{
                "database_name": "fake",
                "server_version": "0",
                "listing_rows": len(listing),
                "calendar_day_rows": len(cal),
                "review_rows": len(rev),
                "listing_null_price": int(listing["price"].isna().sum()),
                "listing_null_bedrooms": int(listing["bedrooms"].isna().sum()),
                "listing_null_beds": int(listing["beds"].isna().sum()),
                "listing_null_bathrooms_text": int(listing["bathrooms_text"].isna().sum()),
                "listing_null_maximum_nights": int(listing["maximum_nights"].isna().sum()),
                "listing_null_instant_bookable": int(listing["instant_bookable"].isna().sum()),
                "listing_null_host_is_superhost": int(listing["host_is_superhost"].isna().sum()),
                "calendar_null_available": int(cal["available"].isna().sum()),
                "review_null_comment_len": int(rev["comment_len"].isna().sum()),
            }]
        )

    def _columns(self, params):
        rows = [
            {"table_name": table, "column_name": col, "data_type": str(dtype)}
            for table, key in (("listing", "listing"), ("calendar_day", "calendar"),
                               ("review", "review"))
            for col, dtype in self.core[key].dtypes.items()
        ]
        return pd.DataFrame(rows)

    def _static(self, params):
        listing = self.core["listing"]
        out = listing.rename(
            columns={"neighbourhood": "neighbourhood_name", "price": "listing_price"}
        )
        out["host_listing_count"] = listing.groupby("host_key")["listing_id"].transform("size")
        return out[[
            "listing_id", "room_type", "property_type", "neighbourhood_name", "accommodates",
            "bedrooms", "beds", "bathrooms_text", "listing_price", "minimum_nights",
            "maximum_nights", "instant_bookable", "host_is_superhost", "host_listing_count",
        ]]

    def _reviews(self, params):
        rev = self.core["review"]
        rev = rev[rev["review_date"] <= _iso(params["cutoff_date"])]
        grouped = rev.groupby("listing_id")
        comment = rev["comment_len"].astype("float64")
        out = pd.DataFrame(
            {
                "total_reviews_before_cutoff": grouped.size(),
                "unique_reviewers_before_cutoff": grouped["reviewer_key"].nunique(),
                "avg_comment_len_before_cutoff": comment.groupby(rev["listing_id"]).mean(),
                "max_comment_len_before_cutoff": comment.groupby(rev["listing_id"]).max(),
                "last_review_date": grouped["review_date"].max(),
            }
        )
        return out.reset_index()

    def _window(self, start, end, after_start=False):
        cal = self.core["calendar"]
        lo, hi = _iso(start), _iso(end)
        mask = (cal["date"] > lo if after_start else cal["date"] >= lo) & (cal["date"] <= hi)
        return cal[mask].assign(avail=lambda d: d["available"].astype(float))

    def _calendar(self, params):
        hist = self._window(params["history_start_date"], params["cutoff_date"])
        recent = hist[hist["date"] >= _iso(params["recent_start_date"])]

        def agg(frame, suffix):
            g = frame.groupby("listing_id")
            return pd.DataFrame(
                {
                    f"calendar_days_observed_{suffix}": g.size(),
                    f"available_days_last_{suffix}": g["available"].sum(),
                    f"available_rate_last_{suffix}": g["avail"].mean(),
                    f"avg_minimum_nights_calendar_last_{suffix}":
                        g["minimum_nights"].mean().astype("float64"),
                    f"avg_maximum_nights_calendar_last_{suffix}":
                        g["maximum_nights"].mean().astype("float64"),
                }
            )

        return agg(hist, "90d").join(agg(recent, "30d"), how="left").reset_index()

    def _label(self, params):
        fut = self._window(params["cutoff_date"], params["label_end_date"], after_start=True)
        g = fut.groupby("listing_id")
        return pd.DataFrame(
            {
                "future_calendar_days_observed_30d": g.size(),
                "future_available_days_30d": g["available"].sum(),
                "future_available_rate_30d": g["avail"].mean(),
            }
        ).reset_index()
