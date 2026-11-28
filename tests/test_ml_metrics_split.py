import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

from airbnb_ops.features.config import TARGET_COLUMN
from airbnb_ops.ml.groups import load_host_groups, neighbourhood_groups
from airbnb_ops.ml.metrics import METRIC_NAMES, confusion, evaluate_scores, positive_scores
from airbnb_ops.ml.split import cross_version_split, grouped_split, stratified_split
from ml_synthetic import make_feature_frame, make_host_groups


def test_metrics_for_a_known_case():
    y = [1, 1, 0, 0, 1, 0]
    scores = [0.9, 0.4, 0.2, 0.6, 0.8, 0.1]
    m, pred = evaluate_scores(y, scores, 0.5)
    assert list(m) == list(METRIC_NAMES)
    assert pred.tolist() == [1, 0, 0, 1, 1, 0]
    assert m["accuracy"] == pytest.approx(4 / 6)
    assert m["precision"] == pytest.approx(2 / 3) and m["recall"] == pytest.approx(2 / 3)
    assert m["roc_auc"] == pytest.approx(8 / 9)
    assert confusion(y, pred) == [[2, 1], [1, 2]]


def test_threshold_moves_precision_and_recall_in_opposite_directions():
    y = [1, 1, 0, 0, 1, 0]
    scores = [0.9, 0.4, 0.2, 0.6, 0.8, 0.1]
    low, _ = evaluate_scores(y, scores, 0.3)
    high, _ = evaluate_scores(y, scores, 0.7)
    assert low["recall"] >= high["recall"] and low["precision"] <= high["precision"] + 1e-9


def test_zero_division_is_zero_and_single_class_auc_is_nan():
    m, _ = evaluate_scores([0, 0, 0], [0.1, 0.2, 0.3], 0.5)
    assert m["precision"] == 0.0 and m["recall"] == 0.0 and m["f1"] == 0.0
    assert np.isnan(m["roc_auc"])


def test_positive_scores_use_classes_not_a_fixed_column():
    X = np.zeros((4, 1))
    model = DummyClassifier(strategy="most_frequent").fit(X, [0, 0, 0, 1])
    assert positive_scores(model, X).tolist() == [0.0] * 4
    only_positive = DummyClassifier(strategy="most_frequent").fit(X, [1, 1, 1, 1])
    assert positive_scores(only_positive, X).tolist() == [1.0] * 4
    only_negative = DummyClassifier(strategy="most_frequent").fit(X, [0, 0, 0, 0])
    assert positive_scores(only_negative, X).tolist() == [0.0] * 4


def test_stratified_split_is_80_20_deterministic_and_keeps_the_rate():
    frame = make_feature_frame()
    a, b = stratified_split(frame), stratified_split(frame)
    assert len(a.test) == 160 and len(a.train) == 640
    assert a.train["listing_id"].tolist() == b.train["listing_id"].tolist()
    assert abs(a.y_train.mean() - a.y_test.mean()) < 0.01
    assert not set(a.train["listing_id"]) & set(a.test["listing_id"])
    assert a.summary()["split_kind"] == "random_split"


def test_grouped_split_never_shares_a_group():
    frame = make_feature_frame()
    groups = make_host_groups(frame)
    part = grouped_split(frame, groups, "host_grouped")
    train_groups = set(part.train["listing_id"].map(groups))
    test_groups = set(part.test["listing_id"].map(groups))
    assert train_groups and test_groups and not train_groups & test_groups
    assert part.summary()["n_groups_test"] == len(test_groups)
    assert TARGET_COLUMN in part.test.columns and "_group" not in part.train.columns


def test_neighbourhood_groups_come_from_the_feature_table():
    frame = make_feature_frame()
    groups = neighbourhood_groups(frame)
    part = grouped_split(frame, groups, "neighbourhood_grouped")
    assert not set(part.train["neighbourhood_name"]) & set(part.test["neighbourhood_name"])


def test_listings_without_a_group_are_dropped_and_counted():
    frame = make_feature_frame()
    groups = make_host_groups(frame).iloc[:-10]
    part = grouped_split(frame, groups, "host_grouped")
    assert part.summary()["rows_without_group"] == 10
    assert len(part.train) + len(part.test) == len(frame) - 10


def test_cross_version_split_tests_on_every_row_of_the_other_version():
    frame = make_feature_frame()
    base = stratified_split(frame)
    other = make_feature_frame(seed=1)
    part = cross_version_split(base, other, "v2")
    assert len(part.test) == len(other) and part.train is base.train
    assert part.kind == "cross_version_v2"


def test_host_groups_are_loaded_through_a_read_only_query():
    class Reader:
        def read_frame(self, sql, params=None):
            assert "host_key" in sql and "DENSE_RANK" in sql
            return pd.DataFrame({"listing_id": [1, 2, 3], "host_group": [1, 1, 2]})

    groups = load_host_groups(Reader())
    assert groups.to_dict() == {1: 1, 2: 1, 3: 2}
