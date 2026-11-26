"""Static checks on the new SQL (no database needed)."""
import re

import pytest

from airbnb_ops.sqlfiles import load_sql

READ_ONLY = [
    "10_source_ranges.sql",
    "11_feature_static_listing.sql",
    "12_feature_reviews.sql",
    "13_feature_calendar.sql",
    "14_label_window.sql",
    "15_source_inspection.sql",
    "16_core_columns.sql",
]
ALL = READ_ONLY + ["04_core_ml_columns.sql"]


@pytest.mark.parametrize("name", ALL)
def test_no_select_star(name):
    assert not re.search(r"select\s+\*", load_sql(name), re.IGNORECASE)


@pytest.mark.parametrize("name", READ_ONLY)
def test_feature_queries_only_read(name):
    sql = re.sub(r"--[^\n]*", "", load_sql(name))  # ignore comments
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE)\b", sql, re.I)


@pytest.mark.parametrize("name", READ_ONLY)
def test_feature_queries_never_return_identity_columns(name):
    select_part = load_sql(name).split("FROM")[0]
    for identity in ("reviewer_key", "host_key", "comments"):
        if identity in select_part:
            # allowed only inside an aggregate or a window clause, never as an output column
            assert re.search(rf"(COUNT\(DISTINCT {identity}\)|PARTITION BY \S*{identity})",
                             select_part), name


def test_parameters_are_bound_not_formatted():
    used = {n: set(re.findall(r"(?<![:\w]):(\w+)", load_sql(n))) for n in READ_ONLY}
    assert used["12_feature_reviews.sql"] == {"cutoff_date"}
    assert used["13_feature_calendar.sql"] == {
        "history_start_date", "recent_start_date", "cutoff_date"}
    assert used["14_label_window.sql"] == {"cutoff_date", "label_end_date"}
    assert used["11_feature_static_listing.sql"] == set()
    assert used["15_source_inspection.sql"] == set()
    assert used["16_core_columns.sql"] == set()


def test_label_window_is_strictly_after_the_cutoff():
    sql = load_sql("14_label_window.sql")
    assert "date > CAST(:cutoff_date AS date)" in sql
    assert "date <= CAST(:label_end_date AS date)" in sql
    assert "date <= CAST(:cutoff_date AS date)" in load_sql("13_feature_calendar.sql")
    assert "review_date <= CAST(:cutoff_date AS date)" in load_sql("12_feature_reviews.sql")


def test_migration_is_additive_and_idempotent():
    sql = load_sql("04_core_ml_columns.sql")
    assert "ADD COLUMN IF NOT EXISTS" in sql
    assert not re.search(r"\b(DROP|TRUNCATE|DELETE)\b", sql, re.I)
    for col in ("bedrooms", "beds", "bathrooms_text", "maximum_nights", "instant_bookable",
                "host_is_superhost", "comment_len"):
        assert col in sql
