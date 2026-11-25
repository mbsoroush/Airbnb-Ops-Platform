"""Pipeline steps against a real Postgres (see conftest.py)."""
import pytest

from airbnb_ops import pipeline
from airbnb_ops.constants import VIEW

pytestmark = pytest.mark.integration

EXTRA_ID = 999999999


def _add_listing(db, price):
    """A listing in a brand-new neighbourhood, with one calendar day inside the real range."""
    db.execute_script(
        f"INSERT INTO core.listing (listing_id, neighbourhood, host_key, price) "
        f"VALUES ({EXTRA_ID}, 'Teststadt', 'k', {price});"
        f"INSERT INTO core.calendar_day (listing_id, date, available) "
        f"SELECT {EXTRA_ID}, MIN(date), true FROM core.calendar_day WHERE listing_id <> {EXTRA_ID}"
    )


def _remove_listing(db):
    db.execute_script(
        f"DELETE FROM core.calendar_day WHERE listing_id = {EXTRA_ID};"
        f"DELETE FROM core.listing WHERE listing_id = {EXTRA_ID}"
    )
    pipeline.refresh_summary(db)


def test_refresh_then_validate_on_real_data(loaded_db):
    loaded_db.execute_script(f"DROP MATERIALIZED VIEW IF EXISTS {VIEW}")

    assert pipeline.refresh_summary(loaded_db)["action"] == "created"
    assert pipeline.refresh_summary(loaded_db)["action"] == "refreshed"
    assert pipeline.refresh_summary(loaded_db, rebuild=True)["action"] == "rebuilt"

    validation = pipeline.validate_summary(loaded_db)
    assert validation["passed"], pipeline.failed_error_checks(validation)


def test_stale_view_is_detected_then_fixed_by_a_refresh(loaded_db):
    pipeline.refresh_summary(loaded_db)
    _add_listing(loaded_db, price=50)
    try:
        stale = pipeline.validate_summary(loaded_db)
        assert not stale["passed"]
        assert pipeline.failed_error_checks(stale) == ["listing_reconciliation"]

        pipeline.refresh_summary(loaded_db)
        assert pipeline.validate_summary(loaded_db)["passed"]
    finally:
        _remove_listing(loaded_db)


def test_negative_price_fails_validation(loaded_db):
    _add_listing(loaded_db, price=-10)
    try:
        pipeline.refresh_summary(loaded_db)
        result = pipeline.validate_summary(loaded_db)
        assert pipeline.failed_error_checks(result) == ["bad_prices"]
    finally:
        _remove_listing(loaded_db)


def test_neighbourhood_without_calendar_data_fails_validation(loaded_db):
    loaded_db.execute_script(
        f"INSERT INTO core.listing (listing_id, neighbourhood, host_key, price) "
        f"VALUES ({EXTRA_ID}, 'Teststadt', 'k', 50)"
    )
    try:
        pipeline.refresh_summary(loaded_db)
        result = pipeline.validate_summary(loaded_db)
        assert pipeline.failed_error_checks(result) == ["bad_availability"]
    finally:
        _remove_listing(loaded_db)
