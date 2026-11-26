"""Real Postgres: the feature SQL must agree with the independent pandas reference.

Uses the separate airbnb_test_ml database (see conftest.py), never the main database.
"""
from datetime import date

import pandas as pd
import pytest

from airbnb_ops.features.artifacts import artifact_paths
from airbnb_ops.features.build import build_feature_dataset, build_feature_frame
from airbnb_ops.features.config import FeatureConfig
from features_reference import FakeReader, load_core_frames

pytestmark = pytest.mark.integration


def test_read_frame_binds_parameters(loaded_ml_db):
    out = loaded_ml_db.read_frame(
        "SELECT CAST(:d AS date) AS d, CAST(:n AS integer) AS n",
        {"d": date(2026, 12, 24), "n": 3},
    )
    assert out.loc[0, "n"] == 3
    assert pd.Timestamp(out.loc[0, "d"]) == pd.Timestamp("2026-12-24")


@pytest.mark.parametrize("cfg", [
    FeatureConfig(),
    FeatureConfig(dataset_version="v2", cutoff_date=date(2027, 1, 3), cutoff_reason="test"),
])
def test_sql_features_match_the_pandas_reference(loaded_ml_db, mini_city_ml, cfg):
    real, real_plan, _, real_report = build_feature_frame(loaded_ml_db, cfg)
    ref, ref_plan, _, _ = build_feature_frame(FakeReader(load_core_frames(mini_city_ml)), cfg)
    assert real_plan == ref_plan
    assert real_report["passed"], real_report["errors"]
    assert real.rule_counts == ref.rule_counts
    pd.testing.assert_frame_equal(
        real.frame, ref.frame, check_dtype=False, check_exact=False, rtol=1e-9
    )


def test_full_build_writes_the_versioned_files(loaded_ml_db, tmp_path):
    result = build_feature_dataset(
        loaded_ml_db, FeatureConfig(dataset_version="itest"), tmp_path / "f"
    )
    assert len(result.frame) == 24
    paths = artifact_paths(tmp_path / "f", "itest")
    assert all(paths[k].exists() for k in ("csv", "metadata", "validation", "pii_audit"))


def test_inspection_on_real_postgres_matches_the_reference(loaded_ml_db, mini_city_ml):
    from airbnb_ops.features.source_inspection import inspect_source

    real = inspect_source(loaded_ml_db)
    ref = inspect_source(FakeReader(load_core_frames(mini_city_ml)))
    assert real["connection"]["status"] == "ok"
    assert real["connection"]["database"] == "airbnb_test_ml"
    assert real["row_counts"] == ref["row_counts"]
    assert real["null_counts"] == ref["null_counts"]
    assert {"listing", "calendar_day", "review"} <= set(real["tables"])
    assert real["tables"]["calendar_day"] == ["listing_id", "date", "available",
                                              "minimum_nights", "maximum_nights"]
    assert real["calendar_price"]["price_columns_present"] == []


def test_feature_sql_never_returns_identity_columns(loaded_ml_db):
    from airbnb_ops.sqlfiles import load_sql

    static = loaded_ml_db.read_frame(load_sql("11_feature_static_listing.sql"))
    assert not {"host_key", "host_id", "host_name"} & set(static.columns)
    reviews = loaded_ml_db.read_frame(
        load_sql("12_feature_reviews.sql"), {"cutoff_date": date(2026, 12, 24)}
    )
    assert not {"reviewer_key", "reviewer_id", "comments"} & set(reviews.columns)
