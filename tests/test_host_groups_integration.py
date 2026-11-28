"""Host groups from the real database, and static checks on the query."""
import re

import pytest

from airbnb_ops.ml.groups import load_host_groups
from airbnb_ops.sqlfiles import load_sql


def test_host_key_only_appears_inside_the_window_clause():
    sql = re.sub(r"--[^\n]*", "", load_sql("20_host_groups.sql"))
    select_list = sql.split("FROM")[0]
    assert re.search(r"DENSE_RANK\(\) OVER \(ORDER BY host_key\)", select_list)
    assert not re.search(r"\bhost_key\s*(,|AS\b)", select_list)
    assert "SELECT *" not in sql.upper()


@pytest.mark.integration
def test_listings_of_one_host_share_a_group_and_no_key_is_returned(loaded_ml_db):
    groups = load_host_groups(loaded_ml_db)
    assert len(groups) == 30 and groups.index.is_unique
    assert groups.loc[5000001] == groups.loc[5000019]  # same host (7000) in the fixture
    assert groups.loc[5000001] != groups.loc[5000002]
    raw = loaded_ml_db.read_frame(load_sql("20_host_groups.sql"))
    assert list(raw.columns) == ["listing_id", "host_group"]
