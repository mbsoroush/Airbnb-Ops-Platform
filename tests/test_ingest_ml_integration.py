"""Ingest of the added columns into a real Postgres (separate test databases)."""
import pandas as pd
import pytest

pytestmark = pytest.mark.integration


def test_old_fixture_without_new_columns_still_loads_with_nulls(loaded_db):
    assert loaded_db.scalar("select count(*) from core.listing") == 20
    assert loaded_db.scalar("select count(*) from core.calendar_day") == 280
    assert loaded_db.scalar("select count(*) from core.review") == 60
    for col in ("bedrooms", "beds", "bathrooms_text", "maximum_nights", "instant_bookable",
                "host_is_superhost"):
        assert loaded_db.scalar(f"select count({col}) from core.listing") == 0, col
    # mini_city has a comments column, so lengths exist; the text itself is never stored
    assert loaded_db.scalar(
        "select count(*) from information_schema.columns "
        "where table_schema = 'core' and column_name in ('comments', 'host_name', 'reviewer_name')"
    ) == 0


def test_new_columns_are_loaded(loaded_ml_db, mini_city_ml):
    assert loaded_ml_db.scalar("select count(*) from core.listing") == 30
    assert loaded_ml_db.scalar("select count(bedrooms) from core.listing") == 29
    assert loaded_ml_db.scalar("select count(maximum_nights) from core.listing") == 29
    assert loaded_ml_db.scalar(
        "select bathrooms_text from core.listing where listing_id = 5000001"
    ) == "Half-bath"
    assert loaded_ml_db.scalar(
        "select count(*) from core.listing where host_is_superhost is null"
    ) == 1
    raw = pd.read_csv(mini_city_ml / "reviews.csv")
    assert loaded_ml_db.scalar("select count(*) from core.review") == raw["id"].nunique()
    assert loaded_ml_db.scalar("select max(comment_len) from core.review") > 0
    assert loaded_ml_db.scalar("select count(*) from core.review where comment_len is null") > 0


def test_migration_is_idempotent(loaded_ml_db):
    from airbnb_ops.ingest.load import schema_sql

    loaded_ml_db.execute_script(schema_sql())
    loaded_ml_db.execute_script(schema_sql())
    assert loaded_ml_db.scalar("select count(*) from core.listing") == 30


def test_duplicate_review_ids_are_removed_across_chunks(loaded_ml_db, mini_city_ml):
    from airbnb_ops.ingest.load import load_city

    raw = pd.read_csv(mini_city_ml / "reviews.csv")
    counts = load_city(loaded_ml_db, mini_city_ml, salt="test-salt", review_chunksize=7)
    assert counts["review"] == raw["id"].nunique() < len(raw)
