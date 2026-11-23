"""Static checks on the shipped SQL (no database needed)."""
import re

import pytest

from airbnb_ops.sqlfiles import load_sql

FILES = [
    "00_core_schema.sql",
    "00_naive_join_antipattern.sql",
    "01_baseline_neighbourhood_summary.sql",
    "02_create_materialized_view.sql",
]


@pytest.mark.parametrize("name", FILES)
def test_no_select_star(name):
    assert not re.search(r"select\s+\*", load_sql(name), re.IGNORECASE)


def test_view_script_defines_two_indexes_incl_unique():
    sql = load_sql("02_create_materialized_view.sql")
    assert len(re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX", sql, re.IGNORECASE)) >= 2
    assert re.search(r"CREATE\s+UNIQUE\s+INDEX", sql, re.IGNORECASE)


def test_nothing_is_created_in_core_by_analytics_sql():
    for name in FILES[1:]:
        assert not re.search(r"CREATE\s+\w+(?:\s+\w+)*\s+core\.", load_sql(name), re.IGNORECASE)
