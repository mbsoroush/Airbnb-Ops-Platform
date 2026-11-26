"""The whole feature build on the mini_city_ml fixture, without Postgres (FakeReader)."""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from airbnb_ops.features.artifacts import VersionExistsError, artifact_paths, sha256_file
from airbnb_ops.features.build import build_feature_dataset, build_feature_frame
from airbnb_ops.features.config import (
    FORBIDDEN_TABLE_COLUMNS,
    MODEL_INPUT_COLUMNS,
    TABLE_COLUMNS,
    FeatureConfig,
)
from features_reference import FakeReader, load_core_frames


@pytest.fixture(scope="module")
def core(mini_city_ml):
    return load_core_frames(mini_city_ml)


def _build(core, **cfg):
    reader = FakeReader(core)
    result, plan, ranges, report = build_feature_frame(reader, FeatureConfig(**cfg))
    return reader, result, plan, ranges, report


def test_cutoff_is_derived_and_parameters_are_bound(core):
    reader, _, plan, ranges, _ = _build(core)
    assert plan.cutoff_date == date(2026, 12, 24)
    assert ranges["calendar_max_date"] == date(2027, 2, 11)
    by_name = {name: params for name, params in reader.calls}
    assert by_name["reviews"] == {"cutoff_date": plan.cutoff_date}
    assert by_name["calendar"]["history_start_date"] == date(2026, 9, 26)
    assert by_name["label"]["label_end_date"] == date(2027, 1, 23)


def test_every_row_rule_is_counted(core):
    _, result, _, _, report = _build(core)
    counts = result.rule_counts
    assert counts["listings_in_core"] == 30
    assert counts["dropped_missing_accommodates"] == 1
    assert counts["dropped_missing_maximum_nights"] == 1
    assert counts["dropped_no_calendar_history"] == 2
    assert counts["dropped_incomplete_history_window"] == 1
    assert counts["dropped_no_label_window"] == 0
    assert counts["dropped_incomplete_label_window"] == 1
    assert counts["filled_property_type_unknown"] == 1
    assert counts["rows_final"] == 24 == len(result.frame)
    assert report["passed"], report["errors"]
    assert 5000004 not in set(result.frame["listing_id"])  # missing accommodates


def test_table_follows_the_contract_and_has_no_forbidden_columns(core):
    _, result, _, _, _ = _build(core)
    frame = result.frame
    assert list(frame.columns) == list(TABLE_COLUMNS)
    assert not set(frame.columns) & set(FORBIDDEN_TABLE_COLUMNS)
    assert frame["listing_id"].is_unique
    assert set(frame["high_demand_proxy"]) == {0, 1}


def test_reviews_after_the_cutoff_are_not_used(core):
    _, result, plan, _, _ = _build(core)
    row = result.frame[result.frame["listing_id"] == 5000011].iloc[0]  # has a 2027-01-15 review
    reviews = core["review"]
    kept = reviews[(reviews["listing_id"] == 5000011) & (reviews["review_date"] <= "2026-12-24")]
    assert len(reviews[reviews["listing_id"] == 5000011]) == len(kept) + 1
    assert row["total_reviews_before_cutoff"] == len(kept)
    last = pd.Timestamp(kept["review_date"].max())
    assert row["days_since_last_review"] == (pd.Timestamp(plan.cutoff_date) - last).days


def test_listings_without_reviews_have_zero_counts_and_missing_text_stats(core):
    _, result, _, _, _ = _build(core)
    row = result.frame[result.frame["listing_id"] == 5000001].iloc[0]  # index 0, no reviews
    assert row["total_reviews_before_cutoff"] == 0
    assert row["unique_reviewers_before_cutoff"] == 0
    assert np.isnan(row["days_since_last_review"])
    assert np.isnan(row["avg_comment_len_before_cutoff"])


def test_label_uses_only_days_after_the_cutoff(core):
    _, result, plan, _, _ = _build(core)
    cal = core["calendar"]
    listing = 5000020
    mine = cal[cal["listing_id"] == listing]
    future = mine[(mine["date"] > "2026-12-24") & (mine["date"] <= "2027-01-23")]
    row = result.frame[result.frame["listing_id"] == listing].iloc[0]
    assert row["future_available_days_30d"] == future["available"].sum()
    assert row["future_calendar_days_observed_30d"] == 30
    hist = mine[(mine["date"] >= "2026-09-26") & (mine["date"] <= "2026-12-24")]
    assert row["available_days_last_90d"] == hist["available"].sum()
    assert row["available_rate_last_90d"] == pytest.approx(hist["available"].mean())


def test_host_listing_count_is_per_host(core):
    _, result, _, _, _ = _build(core)
    hosts = core["listing"].groupby("host_key")["listing_id"].size()
    row = result.frame[result.frame["listing_id"] == 5000001].iloc[0]
    host_key = core["listing"].set_index("listing_id").loc[5000001, "host_key"]
    assert row["host_listing_count"] == hosts[host_key] == 2


def test_missing_values_follow_the_documented_rules(core):
    _, result, _, _, _ = _build(core)
    row = result.frame.set_index("listing_id")
    assert row.loc[5000001, "bathrooms"] == 0.5 and np.isnan(row.loc[5000001, "listing_price"])
    assert row.loc[5000002, "bathrooms"] == 1.5
    assert row.loc[5000003, "property_type"] == "unknown"
    assert not row.loc[5000003, "instant_bookable"] and not row.loc[5000003, "host_is_superhost"]


def test_files_metadata_and_report_are_written(core, tmp_path):
    result = build_feature_dataset(
        FakeReader(core),
        FeatureConfig(dataset_version="t1"),
        tmp_path / "f",
        reports_dir=tmp_path / "r",
    )
    paths = artifact_paths(tmp_path / "f", "t1")
    for key in ("csv", "metadata", "validation", "pii_audit"):
        assert paths[key].exists()
    meta = json.loads(paths["metadata"].read_text())
    assert meta["files"]["csv"]["sha256"] == sha256_file(paths["csv"])
    assert meta["model_input_columns"] == list(MODEL_INPUT_COLUMNS)
    assert meta["cutoff"]["selection_rule"] == "earliest_valid"
    assert meta["source"]["snapshot_date_proxy"] == "2026-09-25"
    assert any("forward-looking" in text for text in meta["limitations"])
    assert meta["source"]["inspection"]["connection"]["status"] == "ok"
    assert meta["source"]["calendar_price"]["used_as_features"] is False
    assert "no price or adjusted_price" in meta["source"]["calendar_price"]["note"]
    assert "never dropped" in meta["unusable_column_rule"]
    assert meta["dropped_unusable_columns"] == []
    assert meta["row_counts"]["dropped_unusable_columns"] == 0
    assert "booked OR blocked by the host" in meta["target_definition"]
    assert json.loads(paths["validation"].read_text())["passed"] is True
    csv = pd.read_csv(paths["csv"])
    assert len(csv) == len(result.frame) == 24
    assert "features_t1.md" in {p.name for p in (tmp_path / "r").iterdir()}
    report_md = (tmp_path / "r" / "features_t1.md").read_text()
    assert "## Source inspection" in report_md and "Database connection: ok" in report_md
    audit = pd.read_csv(paths["pii_audit"])
    assert {"host_key", "reviewer_key", "comments", "bathrooms_text"} <= set(audit["column"])


def test_rebuilding_the_same_version_is_idempotent_but_changed_content_is_refused(core, tmp_path):
    cfg = FeatureConfig(dataset_version="t2")
    build_feature_dataset(FakeReader(core), cfg, tmp_path)
    build_feature_dataset(FakeReader(core), cfg, tmp_path)  # same content: fine
    changed = {**core, "calendar": core["calendar"].assign(available=lambda d: ~d["available"])}
    with pytest.raises(VersionExistsError, match="different content"):
        build_feature_dataset(FakeReader(changed), cfg, tmp_path)
    build_feature_dataset(FakeReader(changed), cfg, tmp_path, overwrite=True)


def test_second_dataset_version_with_a_configured_cutoff(core):
    _, result, plan, _, report = _build(
        core, dataset_version="v2", cutoff_date=date(2027, 1, 3), cutoff_reason="comparison"
    )
    assert plan.selection_rule == "configured"
    assert report["passed"], report["errors"]
    assert (result.frame["cutoff_date"] == "2027-01-03").all()


def test_empty_calendar_gives_a_clear_error(core):
    empty = {**core, "calendar": core["calendar"].iloc[0:0]}
    with pytest.raises(ValueError, match="calendar_day is empty"):
        build_feature_frame(FakeReader(empty), FeatureConfig())
