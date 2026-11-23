"""Neighbourhood-level aggregation."""
import pandas as pd

REQUIRED_LISTING_COLUMNS = [
    "listing_id",
    "neighbourhood",
    "price",
    "minimum_nights",
    "availability_365",
    "number_of_reviews",
]

OUTPUT_COLUMNS = [
    "neighbourhood",
    "num_listings",
    "avg_price",
    "median_price",
    "avg_minimum_nights",
    "availability_365_avg",
    "total_reviews",
    "reviews_per_listing",
    "tourism_segment",
    "priority_level",
]


def build_neighbourhood_summary(listings: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_LISTING_COLUMNS if c not in listings.columns]
    if missing:
        raise ValueError(f"Listings missing required columns: {missing}")

    summary = (
        listings.groupby("neighbourhood", as_index=False)
        .agg(
            num_listings=("listing_id", "count"),
            avg_price=("price", "mean"),
            median_price=("price", "median"),
            avg_minimum_nights=("minimum_nights", "mean"),
            availability_365_avg=("availability_365", "mean"),
            total_reviews=("number_of_reviews", "sum"),
        )
    )
    summary["reviews_per_listing"] = summary["total_reviews"] / summary["num_listings"]

    # Join segment metadata after aggregation; fill gaps with "unknown".
    seg_cols = ["neighbourhood", "tourism_segment", "priority_level"]
    summary = summary.merge(segments[seg_cols], on="neighbourhood", how="left")
    summary[["tourism_segment", "priority_level"]] = summary[
        ["tourism_segment", "priority_level"]
    ].fillna("unknown")

    numeric = ["avg_price", "median_price", "avg_minimum_nights",
               "availability_365_avg", "reviews_per_listing"]
    summary[numeric] = summary[numeric].round(2)
    return summary[OUTPUT_COLUMNS]
