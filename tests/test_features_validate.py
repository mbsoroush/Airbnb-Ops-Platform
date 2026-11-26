import pandas as pd
import pytest

from airbnb_ops.features.build import build_feature_frame
from airbnb_ops.features.config import FeatureConfig
from airbnb_ops.features.validate import (
    FeatureValidationError,
    assert_valid,
    validate_feature_frame,
)
from features_reference import FakeReader, load_core_frames


@pytest.fixture(scope="module")
def built(mini_city_ml):
    result, plan, _, report = build_feature_frame(
        FakeReader(load_core_frames(mini_city_ml)), FeatureConfig()
    )
    return result.frame, plan


def _validate(frame, plan):
    return validate_feature_frame(frame, plan, FeatureConfig())


def test_clean_table_passes_and_reports_statistics(built):
    frame, plan = built
    report = _validate(frame, plan)
    assert report["passed"] and not report["errors"]
    assert all(report["checks"].values())
    assert report["n_rows"] == 24
    assert {d["high_demand_proxy"] for d in report["label_distribution"]} == {0, 1}
    assert report["calendar_coverage_summary"]["min"] == 30.0
    assert report["listing_price_summary"]["missing_rate"] > 0
    rates = [row["missing_rate"] for row in report["missing_report"]]
    assert rates == sorted(rates, reverse=True)
    assert_valid(report)


def _fails(frame, plan, check):
    report = _validate(frame, plan)
    assert not report["passed"]
    assert report["checks"][check] is False
    with pytest.raises(FeatureValidationError):
        assert_valid(report)


def test_future_column_among_model_inputs_is_rejected(built):
    frame, plan = built
    bad = frame.rename(columns={"available_days_last_30d": "future_available_days_x"})
    _fails(bad, plan, "no_future_leakage_in_model_inputs")


def test_forbidden_identity_column_is_rejected(built):
    frame, plan = built
    _fails(frame.assign(host_key="abc"), plan, "no_forbidden_columns")
    _fails(frame.assign(reviewer_key="abc"), plan, "no_forbidden_columns")


def test_missing_or_single_class_target_is_rejected(built):
    frame, plan = built
    _fails(frame.assign(high_demand_proxy=1), plan, "both_classes_present")
    _fails(frame.assign(high_demand_proxy=frame["high_demand_proxy"].astype(float).where(
        frame.index > 0)), plan, "target_not_missing")


def test_label_that_disagrees_with_the_rule_is_rejected(built):
    frame, plan = built
    flipped = frame.assign(high_demand_proxy=1 - frame["high_demand_proxy"])
    _fails(flipped, plan, "label_matches_rule")


def test_incomplete_label_window_is_rejected(built):
    frame, plan = built
    bad = frame.copy()
    bad.loc[0, "future_calendar_days_observed_30d"] = 29
    _fails(bad, plan, "label_window_complete")


def test_duplicate_rows_and_out_of_range_values_are_rejected(built):
    frame, plan = built
    _fails(pd.concat([frame, frame.iloc[[0]]], ignore_index=True), plan,
           "no_duplicate_listing_cutoff")
    bad = frame.copy()
    bad.loc[0, "available_rate_last_30d"] = 1.5
    _fails(bad, plan, "rates_in_unit_interval")


def test_wrong_column_order_or_wrong_cutoff_is_rejected(built):
    frame, plan = built
    _fails(frame[list(reversed(frame.columns))], plan, "column_contract")
    _fails(frame.assign(cutoff_date="2020-01-01"), plan, "cutoff_and_version_constant")


def test_empty_table_is_rejected(built):
    frame, plan = built
    report = _validate(frame.iloc[0:0], plan)
    assert not report["passed"] and report["checks"]["has_rows"] is False
