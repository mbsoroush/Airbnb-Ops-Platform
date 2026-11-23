"""Loads the mini fixture into a real Postgres (separate test database, see conftest.py)."""
import pytest

pytestmark = pytest.mark.integration


def test_load_city_roundtrip(test_db, mini_city):
    from airbnb_ops.ingest.load import load_city

    counts = load_city(test_db, mini_city, salt="test-salt")
    assert counts == {"listing": 20, "calendar_day": 280, "review": 60}

    # idempotent: a second run truncates and reloads the same rows
    assert load_city(test_db, mini_city, salt="test-salt") == counts
    assert test_db.scalar("select count(*) from core.listing") == 20

    # no PII-looking columns in the core schema
    leaked = test_db.scalar(
        """select count(*) from information_schema.columns
           where table_schema = 'core'
             and column_name in ('host_id','host_name','reviewer_id','reviewer_name','comments')"""
    )
    assert leaked == 0

    # referential integrity and type handling
    assert test_db.scalar(
        "select count(*) from core.calendar_day c left join core.listing l using (listing_id) "
        "where l.listing_id is null"
    ) == 0
    assert test_db.scalar("select max(price) from core.listing") == 1250
    assert test_db.scalar("select count(*) from core.listing where price is null") == 1
