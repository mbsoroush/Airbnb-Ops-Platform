import numpy as np
import pandas as pd
import pytest

from airbnb_ops.features.config import TABLE_COLUMNS
from airbnb_ops.features.source_inspection import describe_calendar_price, inspect_source
from airbnb_ops.features.validate import drop_unusable_columns, find_unusable_columns
from features_reference import FakeReader, load_core_frames


@pytest.fixture(scope="module")
def inspection(mini_city_ml):
    return inspect_source(FakeReader(load_core_frames(mini_city_ml)))


def test_connection_and_table_sizes_are_reported(inspection):
    assert inspection["connection"]["status"] == "ok"
    assert inspection["row_counts"]["listing_rows"] == 30
    assert inspection["row_counts"]["calendar_day_rows"] > 3000
    assert inspection["row_counts"]["review_rows"] == 51


def test_missing_values_are_counted(inspection):
    nulls = inspection["null_counts"]
    assert nulls["listing_null_price"] == 1  # index 0
    assert nulls["listing_null_bedrooms"] == 1
    assert nulls["listing_null_maximum_nights"] == 1  # index 4
    assert nulls["listing_null_host_is_superhost"] == 1  # index 2
    assert nulls["review_null_comment_len"] > 0


def test_tables_and_columns_are_listed_without_free_text(inspection):
    tables = inspection["tables"]
    assert set(tables) == {"listing", "calendar_day", "review"}
    assert "date" in tables["calendar_day"] or "available" in tables["calendar_day"]
    assert "comment_len" in tables["review"]
    for forbidden in ("comments", "host_name", "reviewer_name", "host_id", "reviewer_id"):
        assert not any(forbidden in cols for cols in tables.values())


def test_calendar_price_note_says_munich_has_none(inspection):
    note = inspection["calendar_price"]
    assert note["price_columns_present"] == [] and note["used_as_features"] is False
    assert "no price or adjusted_price" in note["note"]


def test_calendar_price_note_when_columns_exist():
    out = describe_calendar_price(["listing_id", "date", "price", "adjusted_price"])
    assert out["price_columns_present"] == ["price", "adjusted_price"]
    assert out["used_as_features"] is False


def _frame():
    return pd.DataFrame(
        {
            "listing_id": [1, 2, 3, 4],
            "room_type": ["a", "a", "a", "a"],  # contract column, constant
            "extra_constant": [1, 1, 1, 1],
            "extra_partly_missing": [np.nan, 1.0, 2.0, np.nan],
            "extra_useful": [1, 2, 3, 4],
        }
    )


def test_unusable_columns_outside_the_contract_are_dropped():
    out, dropped, kept = drop_unusable_columns(_frame())
    assert dropped == ["extra_constant"]
    assert "extra_useful" in out.columns and "extra_constant" not in out.columns
    assert kept == ["room_type"]
    assert "room_type" in out.columns  # contract columns are never dropped
    assert "room_type" in TABLE_COLUMNS


def test_mostly_missing_columns_count_as_unusable():
    frame = pd.DataFrame({"x": [np.nan] * 99 + [1.0], "y": range(100)})
    assert find_unusable_columns(frame) == ["x"]


def test_nothing_is_dropped_from_the_real_feature_table(mini_city_ml):
    from airbnb_ops.features.build import build_feature_frame
    from airbnb_ops.features.config import FeatureConfig

    result, _, _, report = build_feature_frame(
        FakeReader(load_core_frames(mini_city_ml)), FeatureConfig()
    )
    assert report["dropped_unusable_columns"] == []
    assert result.rule_counts["dropped_unusable_columns"] == 0
