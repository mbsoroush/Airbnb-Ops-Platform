from datetime import date

import pytest

from airbnb_ops.features.config import (
    FORBIDDEN_MODEL_INPUTS,
    LABEL_ONLY_COLUMNS,
    MODEL_INPUT_COLUMNS,
    TABLE_COLUMNS,
    FeatureConfig,
)
from airbnb_ops.features.cutoff import plan_cutoff

CAL_MIN, CAL_MAX = date(2026, 9, 25), date(2027, 9, 25)


def test_contract_has_26_unique_model_inputs_without_leakage():
    assert len(MODEL_INPUT_COLUMNS) == 26 == len(set(MODEL_INPUT_COLUMNS))
    assert not any(c.startswith("future_") for c in MODEL_INPUT_COLUMNS)
    assert not set(MODEL_INPUT_COLUMNS) & set(LABEL_ONLY_COLUMNS)
    assert len(TABLE_COLUMNS) == len(set(TABLE_COLUMNS))


def test_forbidden_inputs_cover_label_window_audit_and_pseudonyms():
    for col in ("future_available_rate_30d", "high_demand_proxy", "cutoff_date",
                "dataset_version", "listing_id", "host_key", "reviewer_key"):
        assert col in FORBIDDEN_MODEL_INPUTS
    assert not set(FORBIDDEN_MODEL_INPUTS) & set(MODEL_INPUT_COLUMNS)


def test_default_cutoff_is_derived_from_the_data():
    plan = plan_cutoff(CAL_MIN, CAL_MAX, FeatureConfig())
    assert plan.cutoff_date == date(2026, 12, 24)
    assert plan.selection_rule == "earliest_valid"
    assert plan.earliest_valid_cutoff == date(2026, 12, 24)
    assert plan.latest_valid_cutoff == date(2027, 8, 26)
    assert plan.history_start_date == date(2026, 9, 26)  # 90 days ending at the cutoff
    assert plan.recent_start_date == date(2026, 11, 25)  # 30 days ending at the cutoff
    assert plan.label_end_date == date(2027, 1, 23)  # 30 days strictly after the cutoff
    assert (plan.cutoff_date - plan.history_start_date).days == 89
    assert (plan.label_end_date - plan.cutoff_date).days == 30


def test_configured_cutoff_records_its_reason():
    cfg = FeatureConfig(
        dataset_version="v2", cutoff_date=date(2027, 2, 22), cutoff_reason="avoid holidays"
    )
    plan = plan_cutoff(CAL_MIN, CAL_MAX, cfg)
    assert plan.cutoff_date == date(2027, 2, 22)
    assert plan.selection_rule == "configured"
    assert plan.selection_reason == "avoid holidays"
    assert plan.as_dict()["cutoff_date"] == "2027-02-22"


@pytest.mark.parametrize("bad", [date(2026, 12, 23), date(2027, 8, 27)])
def test_cutoff_outside_valid_range_is_rejected(bad):
    with pytest.raises(ValueError, match="outside the valid range"):
        plan_cutoff(CAL_MIN, CAL_MAX, FeatureConfig(cutoff_date=bad))


def test_calendar_too_short_is_rejected():
    with pytest.raises(ValueError, match="too short"):
        plan_cutoff(CAL_MIN, date(2026, 12, 1), FeatureConfig())


@pytest.mark.parametrize("bad_version", ["", "../x", "v 1", "v1/evil"])
def test_version_must_be_filename_safe(bad_version):
    with pytest.raises(ValueError, match="dataset_version"):
        FeatureConfig(dataset_version=bad_version)


def test_window_lengths_and_threshold_are_guarded():
    with pytest.raises(ValueError, match="fixed"):
        FeatureConfig(past_window_days=60)
    with pytest.raises(ValueError, match="threshold"):
        FeatureConfig(label_threshold=1.5)
