import numpy as np
import pandas as pd

from airbnb_ops.features.config import (
    BOOLEAN_COLUMNS,
    CATEGORICAL_COLUMNS,
    LOG1P_COLUMNS,
    MODEL_INPUT_COLUMNS,
    NUMERIC_COLUMNS,
    PREPROCESSING_CONTRACT,
)
from airbnb_ops.ml.columns import make_column_plan, normalize_input_frame
from ml_synthetic import make_feature_frame


def test_contract_partitions_the_26_model_inputs():
    groups = [CATEGORICAL_COLUMNS, BOOLEAN_COLUMNS, NUMERIC_COLUMNS]
    flat = [c for g in groups for c in g]
    assert sorted(flat) == sorted(MODEL_INPUT_COLUMNS) and len(flat) == 26
    assert set(LOG1P_COLUMNS) <= set(NUMERIC_COLUMNS)
    assert PREPROCESSING_CONTRACT["log1p_columns"] == list(LOG1P_COLUMNS)
    assert "listing_price" in LOG1P_COLUMNS


def test_constant_instant_bookable_is_excluded_from_the_model_only():
    frame = make_feature_frame()
    plan = make_column_plan(frame)
    assert plan.excluded_constant == ("instant_bookable",)
    assert "instant_bookable" in plan.input_columns  # the request contract is unchanged
    assert "instant_bookable" not in plan.used_columns
    assert plan.boolean == ("host_is_superhost",)
    assert len(plan.input_columns) == 26
    assert plan.leakage_columns == ()


def test_varying_instant_bookable_would_be_used():
    frame = make_feature_frame()
    frame["instant_bookable"] = np.arange(len(frame)) % 2 == 0
    assert make_column_plan(frame).excluded_constant == ()


def test_leaky_column_is_added_only_when_requested():
    plan = make_column_plan(make_feature_frame(), ("future_available_rate_30d",))
    assert plan.leakage_columns == ("future_available_rate_30d",)
    assert "future_available_rate_30d" in plan.numeric
    assert "future_available_rate_30d" not in make_column_plan(make_feature_frame()).used_columns


def test_plan_as_dict_lists_what_the_model_uses():
    info = make_column_plan(make_feature_frame()).as_dict()
    assert info["excluded_constant_columns"] == ["instant_bookable"]
    assert set(info["log1p_columns"]) == set(LOG1P_COLUMNS)


def test_normalize_handles_json_style_nulls_and_python_bools():
    X = pd.DataFrame(
        {
            "listing_price": [None, 120.5],
            "flag": [True, None],
            "room_type": ["Private room", None],
            "untouched": [1, 2],
        }
    )
    out = normalize_input_frame(X, ["listing_price"], ["flag"], ["room_type"])
    assert out["listing_price"].dtype == "float64" and np.isnan(out.loc[0, "listing_price"])
    assert out["flag"].tolist()[0] == 1.0 and np.isnan(out.loc[1, "flag"])
    assert out.loc[0, "room_type"] == "Private room" and pd.isna(out.loc[1, "room_type"])
    assert out["untouched"].tolist() == [1, 2]
    assert X.loc[1, "flag"] is None  # the input frame is not modified
