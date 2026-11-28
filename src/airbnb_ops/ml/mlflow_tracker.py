"""The only module that imports MLflow: a thin adapter that implements the Tracker protocol."""
from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import pandas as pd


class TrackingUnavailableError(RuntimeError):
    """The MLflow tracking server cannot be reached."""


def _scrub(value):
    """NaN -> None, numpy scalars -> Python values, recursively (strict JSON has no NaN)."""
    if isinstance(value, dict):
        return {str(k): _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    return value


def _jsonable(payload: Mapping[str, Any]) -> dict:
    return json.loads(json.dumps(_scrub(payload), default=str))


class _MlflowRun:
    def __init__(self, run_id: str):
        self.run_id = run_id

    def set_tags(self, tags: Mapping[str, str]) -> None:
        import mlflow

        mlflow.set_tags({k: str(v) for k, v in tags.items()})

    def log_params(self, params: Mapping[str, Any]) -> None:
        import mlflow

        mlflow.log_params({k: str(v) for k, v in params.items()})

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        import mlflow

        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})

    def log_dict(self, payload: Mapping[str, Any], artifact_file: str) -> None:
        import mlflow

        mlflow.log_dict(_jsonable(payload), artifact_file)

    def log_confusion_matrix(
        self, matrix: Sequence[Sequence[int]], labels: Sequence[str], artifact_file: str
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import mlflow

        fig, ax = plt.subplots(figsize=(4.5, 4))
        ax.imshow(matrix, cmap="Blues")
        ax.set_xticks(range(len(labels)), labels, rotation=20, ha="right")
        ax.set_yticks(range(len(labels)), labels)
        ax.set_xlabel("predicted")
        ax.set_ylabel("actual")
        for i, row in enumerate(matrix):
            for j, value in enumerate(row):
                ax.text(j, i, str(value), ha="center", va="center")
        fig.tight_layout()
        mlflow.log_figure(fig, artifact_file)
        plt.close(fig)

    def log_model(self, pipeline: Any, input_example: pd.DataFrame) -> None:
        import mlflow.sklearn

        mlflow.sklearn.log_model(pipeline, artifact_path="model", input_example=input_example)


class MlflowTracker:
    def __init__(self, tracking_uri: str, experiment_name: str):
        import mlflow
        from mlflow import MlflowClient

        self._mlflow = mlflow
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        mlflow.set_tracking_uri(tracking_uri)
        self._client = MlflowClient()
        try:
            self._client.search_experiments(max_results=1)
            mlflow.set_experiment(experiment_name)
        except Exception as exc:  # noqa: BLE001 - any connection failure gets the same hint
            raise TrackingUnavailableError(
                f"Cannot reach MLflow at {tracking_uri} ({type(exc).__name__}). "
                "Start the local server with `make mlflow-up`, or run with --dry-run."
            ) from exc
        self._experiment_id = mlflow.get_experiment_by_name(experiment_name).experiment_id

    @contextmanager
    def start_run(self, run_name: str) -> Iterator[_MlflowRun]:
        with self._mlflow.start_run(run_name=run_name) as run:
            self._mlflow.set_tag("mlflow_version", self._mlflow.__version__)
            yield _MlflowRun(run.info.run_id)

    def set_run_tags(self, run_id: str, tags: Mapping[str, str]) -> None:
        for key, value in tags.items():
            self._client.set_tag(run_id, key, str(value))

    def clear_tags(self, keys: Sequence[str]) -> int:
        changed = set()
        for key in keys:
            runs = self._client.search_runs(
                [self._experiment_id], filter_string=f"tags.{key} = 'true'", max_results=1000
            )
            for run in runs:
                self._client.delete_tag(run.info.run_id, key)
                changed.add(run.info.run_id)
        return len(changed)

    def runs_table(self) -> pd.DataFrame:
        """The assignment's comparison table, straight from mlflow.search_runs."""
        return self._mlflow.search_runs(experiment_names=[self.experiment_name])
