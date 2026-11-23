"""Materialized view vs baseline, against a real Postgres (see conftest.py)."""
import pytest

from airbnb_ops import analytics

pytestmark = pytest.mark.integration


def _by_neighbourhood(columns, rows):
    return {r[0]: dict(zip(columns, r, strict=True)) for r in rows}


def test_view_matches_baseline_exactly(loaded_db):
    analytics.build_summary_view(loaded_db)
    base_cols, base_rows = loaded_db.fetch(analytics.baseline_sql())
    view_cols, view_rows = loaded_db.fetch(
        f"select {', '.join(analytics.SUMMARY_COLUMNS)} from {analytics.VIEW}"
    )
    base = _by_neighbourhood(base_cols, base_rows)
    view = _by_neighbourhood(view_cols, view_rows)

    assert base.keys() == view.keys() and len(base) > 0
    for hood in base:
        for col in analytics.SUMMARY_COLUMNS[1:]:
            assert base[hood][col] == view[hood][col], f"{hood}.{col} differs"


def test_view_has_indexes_and_365_rate(loaded_db):
    analytics.build_summary_view(loaded_db)
    n_indexes = loaded_db.scalar(
        "select count(*) from pg_indexes where schemaname = 'analytics' "
        "and tablename = 'mv_airbnb_neighbourhood_summary'"
    )
    assert n_indexes >= 2
    _, rows = loaded_db.fetch(f"select availability_365_rate from {analytics.VIEW}")
    assert all(0 <= float(r[0]) <= 1 for r in rows if r[0] is not None)


def test_concurrent_refresh_keeps_rows(loaded_db):
    analytics.build_summary_view(loaded_db)
    before = loaded_db.scalar(f"select count(*) from {analytics.VIEW}")
    analytics.refresh_summary_view(loaded_db, concurrently=True)
    assert loaded_db.scalar(f"select count(*) from {analytics.VIEW}") == before


def test_naive_join_is_wrong_but_baseline_is_right(loaded_db):
    """The anti-pattern weights listings by review count; the baseline does not."""
    _, naive = loaded_db.fetch(analytics.naive_sql())
    cols, base = loaded_db.fetch(analytics.baseline_sql())
    i = cols.index("avg_price")
    truth = {r[0]: float(r[i]) for r in base if r[i] is not None}
    naive_price = {r[0]: float(r[2]) for r in naive if r[2] is not None}
    assert any(abs(naive_price[h] - truth[h]) > 0.01 for h in naive_price if h in truth)


def test_dashboard_query_reads_view_only(loaded_db):
    sql = analytics.dashboard_sql().lower()
    assert "core." not in sql and analytics.VIEW in sql
    cols, rows = loaded_db.fetch(analytics.dashboard_sql())
    assert "availability_365_rate" in cols and len(rows) > 0
