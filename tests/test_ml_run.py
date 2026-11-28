import numpy as np
import pytest

from airbnb_ops.features.config import FORBIDDEN_MODEL_INPUTS, MODEL_INPUT_COLUMNS
from airbnb_ops.ml.run import RunContext, build_run_context, execute_run
from airbnb_ops.ml.specs import LEAKAGE_COLUMN, RunSpec, default_run_specs
from airbnb_ops.ml.split import stratified_split
from airbnb_ops.ml.tracking import InMemoryTracker
from ml_synthetic import make_feature_frame, make_loaded_dataset

REQUIRED_ARTIFACTS = {
    "confusion_matrix.png", "classification_report.json", "feature_columns.json",
    "dataset_metadata_snapshot.json", "model",
}
REQUIRED_TAGS = {
    "leakage_status", "known_defect", "model_family", "dataset_version", "dataset_sha256",
    "cutoff_date", "git_commit", "sklearn_version", "random_state",
}


@pytest.fixture(scope="module")
def setup():
    dataset = make_loaded_dataset()
    split = stratified_split(dataset.frame)
    context = build_run_context(dataset, cv_folds=3)
    specs = {s.name: s for s in default_run_specs()}
    return split, context, specs


def _run(setup, name, **kwargs):
    split, context, specs = setup
    tracker = InMemoryTracker()
    result = execute_run(specs[name], split, context, tracker, **kwargs)
    return result, tracker.get(result.run_id)


def test_a_clean_run_logs_tags_params_metrics_artifacts_and_the_model(setup):
    result, run = _run(setup, "v3_balanced_logistic_regression")
    assert REQUIRED_TAGS <= set(run.tags)
    assert run.tags["leakage_status"] == "clean" and run.tags["known_defect"] == "none"
    assert run.tags["model_family"] == "logistic_regression"
    assert run.tags["dataset_sha256"] == "a" * 64 and run.tags["dataset_version"] == "v1"
    assert REQUIRED_ARTIFACTS <= set(run.artifact_names)
    for metric in ("accuracy", "precision", "recall", "f1", "roc_auc", "cv_f1", "cv_roc_auc"):
        assert metric in run.metrics
    for param in ("threshold", "random_state", "class_weight", "test_size", "cv_folds"):
        assert param in run.params
    assert run.params["excluded_constant_columns"] == "instant_bookable"
    assert result.run_id == run.run_id and result.is_standard


def test_the_leaky_run_is_tagged_and_looks_suspiciously_good(setup):
    leaky, run = _run(setup, "v0_leaky_logistic_regression")
    clean, _ = _run(setup, "v2_clean_logistic_regression")
    assert run.tags["leakage_status"] == "leaky"
    assert run.tags["known_defect"] == "uses future_available_rate_30d"
    assert run.tags["selection_candidate"] == "false"
    assert LEAKAGE_COLUMN in run.dicts["feature_columns.json"]["input_columns"]
    assert leaky.metrics["roc_auc"] > clean.metrics["roc_auc"]
    assert leaky.metrics["roc_auc"] > 0.97


def test_the_dummy_baseline_has_no_skill(setup):
    result, run = _run(setup, "v1_dummy_baseline")
    assert result.metrics["roc_auc"] == 0.5
    assert run.tags["model_family"] == "dummy" and run.tags["selection_candidate"] == "false"


def test_the_threshold_is_a_param_and_changes_the_metrics(setup):
    low, _ = _run(setup, "v4_threshold_0.30")
    high, _ = _run(setup, "v4_threshold_0.60")
    assert low.params["threshold"] == 0.30 and high.params["threshold"] == 0.60
    assert low.metrics["recall"] >= high.metrics["recall"]
    assert low.metrics["roc_auc"] == pytest.approx(high.metrics["roc_auc"])


def test_random_forest_logs_its_hyperparameters(setup):
    _, run = _run(setup, "v5b_random_forest_shallow")
    for param in ("n_estimators", "max_depth", "min_samples_leaf", "class_weight", "random_state"):
        assert param in run.params


def test_runs_are_reproducible(setup):
    a, _ = _run(setup, "v5b_random_forest_shallow")
    b, _ = _run(setup, "v5b_random_forest_shallow")
    assert a.metrics == b.metrics


def test_the_feature_columns_artifact_describes_the_model_input(setup):
    _, run = _run(setup, "v2_clean_logistic_regression")
    info = run.dicts["feature_columns.json"]
    assert info["input_columns"] == list(MODEL_INPUT_COLUMNS)
    assert "instant_bookable" in info["excluded_constant_columns"]
    assert "instant_bookable" not in info["used_columns"]
    assert info["leakage_columns_included"] == []


def test_the_dataset_metadata_snapshot_is_logged(setup):
    _, run = _run(setup, "v2_clean_logistic_regression")
    assert run.dicts["dataset_metadata_snapshot.json"]["dataset_version"] == "v1"


def test_a_clean_run_cannot_use_forbidden_columns(setup):
    split, context, _ = setup
    bad = RunSpec("bad", "logistic_regression", "clean", "x", {"max_iter": 100},
                  extra_columns=(LEAKAGE_COLUMN,))
    with pytest.raises(ValueError, match="must not use"):
        execute_run(bad, split, context, InMemoryTracker())
    assert LEAKAGE_COLUMN in FORBIDDEN_MODEL_INPUTS


def test_no_group_labels_or_identifiers_reach_the_tracker(setup):
    _, run = _run(setup, "v3_balanced_logistic_regression")
    blob = str(run.dicts) + str(run.params) + str(run.tags)
    for forbidden in ("host_group", "host_key", "reviewer_key", "listing_id"):
        assert forbidden not in blob.replace("host_listing_count", "")


def test_nan_metrics_are_not_logged():
    frame = make_feature_frame(n=60)
    frame["high_demand_proxy"] = 1  # single class: roc_auc is undefined
    dataset = make_loaded_dataset(frame)
    context = build_run_context(dataset, cv_folds=0)
    split = stratified_split(frame.assign(high_demand_proxy=[0, 1] * 30))
    split = type(split)(split.train.assign(high_demand_proxy=1), split.test.assign(
        high_demand_proxy=1), "random_split", {})
    spec = next(s for s in default_run_specs() if s.name == "v1_dummy_baseline")
    tracker = InMemoryTracker()
    result = execute_run(spec, split, context, tracker, cv_folds=0)
    assert np.isnan(result.metrics["roc_auc"])
    assert "roc_auc" not in tracker.get(result.run_id).metrics


def test_the_logged_input_example_has_no_integer_columns(setup):
    _, run = _run(setup, "v2_clean_logistic_regression")
    example = run.examples[0]
    assert len(example) == 5 and list(example.columns)[:3] == ["room_type", "property_type",
                                                              "neighbourhood_name"]
    assert not list(example.select_dtypes("integer").columns)


def test_run_context_records_git_info_and_versions(setup):
    _, context, _ = setup
    assert isinstance(context, RunContext) and context.git_commit
    _, run = _run(setup, "v2_clean_logistic_regression")
    assert run.tags["sklearn_version"] and run.tags["python_version"]
