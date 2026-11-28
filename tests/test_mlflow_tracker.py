"""Needs the real `mlflow` package (the ml extra). Uses a file store in tmp_path: no server."""
import mlflow
import pytest

from airbnb_ops.ml.mlflow_tracker import MlflowTracker, TrackingUnavailableError
from airbnb_ops.ml.orchestrate import run_experiments
from airbnb_ops.ml.specs import default_run_specs
from ml_synthetic import make_loaded_dataset

SMALL = {"v0_leaky_logistic_regression", "v1_dummy_baseline", "v3_balanced_logistic_regression",
         "v5b_random_forest_shallow"}


@pytest.fixture()
def tracker(tmp_path):
    return MlflowTracker(f"file:{tmp_path / 'mlruns'}", "test_experiment")


def _run(tracker):
    specs = [s for s in default_run_specs() if s.name in SMALL]
    return run_experiments(make_loaded_dataset(), tracker, specs=specs, cv_folds=3)


def test_runs_land_in_mlflow_with_tags_metrics_and_artifacts(tracker):
    out = _run(tracker)
    client = mlflow.MlflowClient()
    run = client.get_run(out.selection.run_id)
    assert run.data.tags["leakage_status"] == "clean"
    assert run.data.tags["selected_for_serving"] == "true"
    assert run.data.tags["production_candidate"] == "true"
    assert run.data.tags["mlflow_version"] == mlflow.__version__
    assert "f1" in run.data.metrics and "cv_f1" in run.data.metrics
    names = {a.path for a in client.list_artifacts(run.info.run_id)}
    assert {"confusion_matrix.png", "classification_report.json", "feature_columns.json",
            "dataset_metadata_snapshot.json", "model"} <= names
    table = tracker.runs_table()
    assert len(table) >= len(SMALL) and "tags.leakage_status" in table.columns


def test_the_logged_model_is_the_full_pipeline_and_predicts(tracker):
    out = _run(tracker)
    model = mlflow.sklearn.load_model(f"runs:/{out.selection.run_id}/model")
    assert list(model.named_steps) == ["normalize", "preprocess", "model"]
    frame = make_loaded_dataset().frame
    cols = out.results[1].columns["input_columns"]
    assert model.predict_proba(frame[cols].head(3)).shape == (3, 2)


def test_only_the_newest_selection_keeps_the_serving_tag(tracker):
    first = _run(tracker)
    second = _run(tracker)
    client = mlflow.MlflowClient()
    assert "selected_for_serving" not in client.get_run(first.selection.run_id).data.tags
    assert client.get_run(second.selection.run_id).data.tags["selected_for_serving"] == "true"


def test_an_unreachable_server_gives_a_clear_error(monkeypatch):
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "2")
    with pytest.raises(TrackingUnavailableError, match="make mlflow-up"):
        MlflowTracker("http://127.0.0.1:9", "x")
