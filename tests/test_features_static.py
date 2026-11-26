import numpy as np
import pandas as pd
import pytest

from airbnb_ops.features.static import clean_static_features, parse_bathrooms


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1 bath", 1.0), ("1.5 baths", 1.5), ("2 shared baths", 2.0), ("0 baths", 0.0),
        ("Half-bath", 0.5), ("Shared half-bath", 0.5), ("Private half-bath", 0.5),
        ("2 half-baths", 1.0),
    ],
)
def test_parse_bathrooms(text, expected):
    assert parse_bathrooms(text) == expected


@pytest.mark.parametrize("text", [None, "", "  ", "unknown", pd.NA, float("nan")])
def test_parse_bathrooms_unknown_is_nan(text):
    assert np.isnan(parse_bathrooms(text))


def _static(**overrides):
    base = {
        "listing_id": [1, 2, 3, 4],
        "room_type": ["Entire home/apt", None, "Private room", "Private room"],
        "property_type": ["Entire condo", "Entire condo", "", "Entire condo"],
        "neighbourhood_name": ["A", "A", "B", "B"],
        "accommodates": [2, 4, None, 3],
        "bedrooms": [1.0, None, 2.0, 1.0],
        "beds": [1.0, 2.0, 2.0, 1.0],
        "bathrooms_text": ["1 bath", "Half-bath", None, "2 baths"],
        "listing_price": [100.0, None, 80.0, 90.0],
        "minimum_nights": [1, 2, 3, None],
        "maximum_nights": [30, 60, 90, 120],
        "instant_bookable": [True, None, False, True],
        "host_is_superhost": [None, True, False, True],
        "host_listing_count": [1, 2, 2, 1],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_rules_fill_drop_and_count():
    out, counts = clean_static_features(_static())
    assert list(out["listing_id"]) == [1, 2]  # 3 lacks accommodates, 4 lacks minimum_nights
    assert counts["listings_in_core"] == 4
    assert counts["dropped_missing_accommodates"] == 1
    assert counts["dropped_missing_minimum_nights"] == 1
    assert counts["dropped_missing_maximum_nights"] == 0
    assert counts["filled_room_type_unknown"] == 1
    assert counts["filled_property_type_unknown"] == 1
    assert counts["filled_instant_bookable_false"] == 1
    assert counts["filled_host_is_superhost_false"] == 1
    assert out.loc[out["listing_id"] == 2, "room_type"].item() == "unknown"
    assert out.loc[out["listing_id"] == 1, "host_is_superhost"].item() is False
    assert out["instant_bookable"].dtype == bool


def test_nullable_numeric_features_stay_missing_and_bathrooms_is_parsed():
    out, _ = clean_static_features(_static())
    assert "bathrooms_text" not in out.columns
    assert list(out["bathrooms"]) == [1.0, 0.5]
    assert np.isnan(out.loc[out["listing_id"] == 2, "listing_price"].item())
    assert np.isnan(out.loc[out["listing_id"] == 2, "bedrooms"].item())
    assert out["accommodates"].dtype == "int64"


def test_duplicate_listing_ids_are_rejected():
    with pytest.raises(ValueError, match="one row per listing_id"):
        clean_static_features(_static(listing_id=[1, 1, 3, 4]))
