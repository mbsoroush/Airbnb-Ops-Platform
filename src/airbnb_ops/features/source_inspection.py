"""Inspection of the source tables: connection check, sizes, missing values, calendar prices.

The numbers go into the dataset metadata and the Markdown report, so every build documents the
data it was made from.
"""
from __future__ import annotations

from typing import Any

from ..sqlfiles import load_sql

ROW_COUNT_KEYS = ("listing_rows", "calendar_day_rows", "review_rows")
NULL_COUNT_KEYS = (
    "listing_null_price",
    "listing_null_bedrooms",
    "listing_null_beds",
    "listing_null_bathrooms_text",
    "listing_null_maximum_nights",
    "listing_null_instant_bookable",
    "listing_null_host_is_superhost",
    "calendar_null_available",
    "review_null_comment_len",
)


def describe_calendar_price(calendar_columns: list[str]) -> dict[str, Any]:
    """Answer the notebook's question: are calendar price / adjusted_price usable?"""
    present = [c for c in ("price", "adjusted_price") if c in calendar_columns]
    if not present:
        note = (
            "core.calendar_day has no price or adjusted_price column (the Munich calendar file "
            "has none), so no calendar price features are built. listing_price comes from "
            "core.listing."
        )
    else:
        note = (
            f"core.calendar_day has {present}, but this contract does not use calendar prices; "
            "listing_price comes from core.listing."
        )
    return {"price_columns_present": present, "used_as_features": False, "note": note}


def inspect_source(reader) -> dict[str, Any]:
    """Run the connection check and inspection queries (read-only)."""
    row = reader.read_frame(load_sql("15_source_inspection.sql")).iloc[0]
    columns = reader.read_frame(load_sql("16_core_columns.sql"))
    tables = {
        str(name): [str(c) for c in group["column_name"]]
        for name, group in columns.groupby("table_name", sort=True)
    }
    return {
        "connection": {
            "status": "ok",
            "database": str(row["database_name"]),
            "server_version": str(row["server_version"]),
        },
        "row_counts": {k: int(row[k]) for k in ROW_COUNT_KEYS},
        "null_counts": {k: int(row[k]) for k in NULL_COUNT_KEYS},
        "tables": tables,
        "calendar_price": describe_calendar_price(tables.get("calendar_day", [])),
    }
