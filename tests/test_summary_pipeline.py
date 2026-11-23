from pathlib import Path

import pandas as pd
import pytest

from airbnb_ops.pii import handle_pii
from airbnb_ops.transform import OUTPUT_COLUMNS, build_neighbourhood_summary
from airbnb_ops.validate import validate_summary

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture()
def summary() -> pd.DataFrame:
    listings = handle_pii(pd.read_csv(RAW / "listings_sample.csv"))
    segments = pd.read_csv(RAW / "neighbourhood_segments.csv")
    return build_neighbourhood_summary(listings, segments)


def test_summary_matches_contract(summary):
    assert list(summary.columns) == OUTPUT_COLUMNS
    assert len(summary) == 5
    row = summary.set_index("neighbourhood").loc["Centrum-West"]
    assert row["num_listings"] == 2
    assert row["avg_price"] == 195.0
    validate_summary(summary)


def test_missing_segment_becomes_unknown():
    listings = handle_pii(pd.read_csv(RAW / "listings_sample.csv"))
    segments = pd.read_csv(RAW / "neighbourhood_segments.csv").iloc[:2]
    out = build_neighbourhood_summary(listings, segments)
    assert (out["tourism_segment"] == "unknown").any()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.iloc[0:0],
        lambda d: d.assign(avg_price=-1),
        lambda d: d.assign(availability_365_avg=400),
        lambda d: d.assign(neighbourhood=None),
        lambda d: d.assign(host_name="x"),
    ],
)
def test_validation_rejects_bad_output(summary, mutate):
    with pytest.raises(ValueError):
        validate_summary(mutate(summary))
