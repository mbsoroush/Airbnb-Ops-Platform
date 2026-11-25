"""Dashboard SQL and the read-only role, against a real Postgres (see conftest.py)."""
from dataclasses import replace

import pytest

from airbnb_ops import analytics
from airbnb_ops.db import Database
from airbnb_ops.metabase.dashboard import default_dashboard

pytestmark = pytest.mark.integration

READER = "airbnb_test_reader"
PASSWORD = "pw'with\"quote%s;--"  # awkward on purpose: must be quoted safely


def test_every_dashboard_query_runs_and_chart_columns_exist(loaded_db):
    analytics.build_summary_view(loaded_db)
    for card in default_dashboard().cards:
        columns, rows = loaded_db.fetch(card.sql)
        assert rows, f"{card.name} returned no rows"
        for key in ("graph.dimensions", "graph.metrics"):
            for column in card.visualization_settings.get(key, []):
                assert column in columns, f"{card.name}: {column} not in {columns}"


def test_reader_role_is_read_only_and_survives_view_rebuilds(loaded_db):
    loaded_db.ensure_reader_role(READER, PASSWORD)
    loaded_db.ensure_reader_role(READER, PASSWORD)  # idempotent
    analytics.build_summary_view(loaded_db)  # DROP + CREATE must not revoke access

    reader = Database(replace(loaded_db.settings, user=READER, password=PASSWORD))
    try:
        columns, rows = reader.fetch(analytics.dashboard_sql())
        assert rows and "availability_365_rate" in columns
        with pytest.raises(Exception, match="permission denied"):
            reader.fetch("select listing_id from core.listing")
        with pytest.raises(Exception, match="permission denied"):
            reader.execute_script("create table analytics.should_not_exist (a int)")
    finally:
        reader.engine.dispose()
