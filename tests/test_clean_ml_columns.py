"""Ingest cleaning for the columns added for the feature dataset."""
import numpy as np
import pandas as pd
import pytest

from airbnb_ops.ingest.clean import (
    LISTING_COLUMNS,
    LISTING_OPTIONAL_USECOLS,
    LISTING_REQUIRED_USECOLS,
    REVIEW_COLUMNS,
    REVIEW_OPTIONAL_USECOLS,
    REVIEW_REQUIRED_USECOLS,
    clean_listings,
    clean_reviews,
    parse_tf,
    select_usecols,
)

SALT = "test-salt"


def test_parse_tf_maps_t_f_and_leaves_other_values_missing():
    out = parse_tf(pd.Series(["t", "f", "T", None, "", "maybe"]))
    assert out.dtype == "boolean"
    assert list(out.iloc[:3]) == [True, False, True]
    assert out.iloc[3:].isna().all()


def test_select_usecols_keeps_optional_columns_that_exist(mini_city, mini_city_ml):
    old = select_usecols(mini_city / "listings.csv", LISTING_REQUIRED_USECOLS,
                         LISTING_OPTIONAL_USECOLS)
    assert old == LISTING_REQUIRED_USECOLS  # mini_city has none of the new columns
    new = select_usecols(mini_city_ml / "listings.csv", LISTING_REQUIRED_USECOLS,
                         LISTING_OPTIONAL_USECOLS)
    assert new == LISTING_REQUIRED_USECOLS + LISTING_OPTIONAL_USECOLS
    assert "host_name" not in new  # names are never read


def test_select_usecols_fails_clearly_when_a_required_column_is_missing(tmp_path):
    path = tmp_path / "listings.csv"
    path.write_text("id,price\n1,$5\n")
    with pytest.raises(ValueError, match="missing required columns"):
        select_usecols(path, LISTING_REQUIRED_USECOLS, LISTING_OPTIONAL_USECOLS)


def test_old_files_without_the_new_columns_still_clean_to_null(mini_city):
    raw = pd.read_csv(mini_city / "listings.csv", usecols=LISTING_REQUIRED_USECOLS)
    out = clean_listings(raw, SALT)
    assert list(out.columns) == LISTING_COLUMNS
    assert out[LISTING_OPTIONAL_USECOLS].isna().all().all()
    reviews = clean_reviews(
        pd.read_csv(mini_city / "reviews.csv", usecols=REVIEW_REQUIRED_USECOLS), SALT
    )
    assert reviews["comment_len"].isna().all()


def test_new_listing_columns_are_parsed(mini_city_ml):
    cols = LISTING_REQUIRED_USECOLS + LISTING_OPTIONAL_USECOLS
    out = clean_listings(pd.read_csv(mini_city_ml / "listings.csv", usecols=cols), SALT)
    assert out["instant_bookable"].dtype == "boolean"
    first = out.iloc[0]  # index 0: no price, no bedrooms, "Half-bath"
    assert np.isnan(first["price"]) and np.isnan(first["bedrooms"])
    assert first["bathrooms_text"] == "Half-bath"
    assert out.iloc[2]["instant_bookable"] is pd.NA and out.iloc[2]["host_is_superhost"] is pd.NA
    assert out["accommodates"].isna().sum() == 1 and out["maximum_nights"].isna().sum() == 1
    assert not {"host_id", "host_name"} & set(out.columns)


def test_comment_length_is_kept_but_comment_text_never(mini_city_ml):
    cols = REVIEW_REQUIRED_USECOLS + REVIEW_OPTIONAL_USECOLS
    raw = pd.read_csv(mini_city_ml / "reviews.csv", usecols=cols)
    out = clean_reviews(raw, SALT)
    assert list(out.columns) == REVIEW_COLUMNS
    assert "comments" not in out.columns
    assert out["review_id"].is_unique and len(out) == len(raw) - 1  # one duplicate dropped
    row = out.iloc[0]
    assert row["comment_len"] == len(raw.loc[raw["id"] == row["review_id"], "comments"].iloc[0])
    assert out["comment_len"].isna().any()  # reviews with an empty comment have no length
    assert (out["reviewer_key"].str.len() == 16).all()
