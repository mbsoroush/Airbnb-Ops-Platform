import io

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from airbnb_ops.features.config import MODEL_INPUT_COLUMNS
from airbnb_ops.ml.columns import make_column_plan
from airbnb_ops.ml.metrics import positive_scores
from airbnb_ops.ml.pipeline import build_pipeline
from ml_synthetic import make_feature_frame


@pytest.fixture(scope="module")
def fitted():
    frame = make_feature_frame()
    plan = make_column_plan(frame)
    cols = list(plan.input_columns)
    pipe = build_pipeline(plan, LogisticRegression(max_iter=2000))
    pipe.fit(frame[cols], frame["high_demand_proxy"])
    return pipe, frame, cols


def test_the_pipeline_handles_missing_values_and_the_price_outlier(fitted):
    pipe, frame, cols = fitted
    assert frame["listing_price"].isna().mean() > 0.2 and frame["listing_price"].max() > 79000
    scores = positive_scores(pipe, frame[cols])
    assert np.isfinite(scores).all() and scores.min() >= 0 and scores.max() <= 1


def test_log1p_keeps_the_outlier_from_dominating(fitted):
    pipe, frame, cols = fitted
    transformed = pipe[:-1].transform(frame[cols])
    assert np.isfinite(transformed).all()
    assert np.abs(transformed).max() < 50  # a raw 79,600 price scaled linearly would be huge


def test_missing_indicators_are_added_for_columns_with_missing_values(fitted):
    pipe, frame, cols = fitted
    imputer = pipe.named_steps["preprocess"].named_transformers_["log_numeric"]["impute"]
    assert imputer.indicator_ is not None
    assert imputer.indicator_.features_.size >= 1


def test_serving_style_single_row_with_nulls_and_python_types(fitted):
    pipe, frame, cols = fitted
    row = {c: frame.iloc[0][c].item() if hasattr(frame.iloc[0][c], "item") else frame.iloc[0][c]
           for c in cols}
    row.update(listing_price=None, bedrooms=None, host_is_superhost=True, instant_bookable=False,
               days_since_last_review=None)
    X = pd.DataFrame([row], columns=cols)
    score = positive_scores(pipe, X)
    assert score.shape == (1,) and 0 <= score[0] <= 1


def test_unknown_category_does_not_break_prediction(fitted):
    pipe, frame, cols = fitted
    X = frame[cols].head(3).copy()
    X["neighbourhood_name"] = "A brand new quarter"
    assert positive_scores(pipe, X).shape == (3,)


def test_the_excluded_constant_column_does_not_change_predictions(fitted):
    pipe, frame, cols = fitted
    X = frame[cols].head(20).copy()
    flipped = X.assign(instant_bookable=True)
    assert np.allclose(positive_scores(pipe, X), positive_scores(pipe, flipped))


def test_pickle_roundtrip_gives_identical_predictions(fitted):
    import joblib

    pipe, frame, cols = fitted
    buffer = io.BytesIO()
    joblib.dump(pipe, buffer)
    buffer.seek(0)
    loaded = joblib.load(buffer)
    X = frame[cols].head(50)
    assert np.allclose(positive_scores(pipe, X), positive_scores(loaded, X))


def test_only_contract_columns_are_inputs_for_a_clean_pipeline(fitted):
    _, _, cols = fitted
    assert cols == list(MODEL_INPUT_COLUMNS)
