"""The shared run helper: every run is trained, evaluated and logged by `execute_run`."""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from ..features.config import FORBIDDEN_MODEL_INPUTS, MODEL_INPUT_COLUMNS
from .columns import make_column_plan
from .data import LoadedDataset
from .metrics import (
    METRIC_NAMES,
    confusion,
    evaluate_scores,
    positive_scores,
    report_dict,
)
from .pipeline import build_pipeline
from .specs import RunSpec, make_estimator
from .split import RANDOM_STATE, TEST_SIZE, SplitData
from .tracking import Tracker

STANDARD = "random_split"


@dataclass(frozen=True)
class RunContext:
    """Everything that identifies the data and the code a run was made with."""

    dataset_version: str
    dataset_sha256: str
    dataset_csv_sha256: str
    dataset_file: str
    cutoff_date: str
    label_threshold: float
    dataset_metadata: dict
    git_commit: str = "unknown"
    git_dirty: str = "unknown"
    random_state: int = RANDOM_STATE
    test_size: float = TEST_SIZE
    cv_folds: int = 5


@dataclass(frozen=True)
class RunResult:
    run_id: str
    name: str
    tags: dict[str, str]
    params: dict[str, Any]
    metrics: dict[str, float]
    columns: dict[str, Any]
    split: dict[str, Any] = field(default_factory=dict)

    @property
    def is_standard(self) -> bool:
        return self.tags.get("evaluation_kind") == STANDARD


def git_info() -> tuple[str, str]:
    """(commit, dirty) of the working tree, or ('unknown', 'unknown') outside a checkout."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        return commit, "true" if status else "false"
    except (OSError, subprocess.SubprocessError):
        return "unknown", "unknown"


def build_run_context(
    dataset: LoadedDataset, cv_folds: int = 5, random_state: int = RANDOM_STATE,
    test_size: float = TEST_SIZE,
) -> RunContext:
    commit, dirty = git_info()
    meta = dataset.metadata
    return RunContext(
        dataset_version=dataset.version,
        dataset_sha256=dataset.sha256,
        dataset_csv_sha256=dataset.csv_sha256,
        dataset_file=dataset.source_file,
        cutoff_date=meta["cutoff"]["cutoff_date"],
        label_threshold=meta["label_threshold"],
        dataset_metadata=meta,
        git_commit=commit,
        git_dirty=dirty,
        random_state=random_state,
        test_size=test_size,
        cv_folds=cv_folds,
    )


def _cv_metrics(pipeline, X, y, folds: int, random_state: int, threshold: float) -> dict:
    if folds < 2:
        return {}
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    proba = cross_val_predict(clone(pipeline), X, y, cv=cv, method="predict_proba")
    metrics, _ = evaluate_scores(y, proba[:, 1], threshold)
    return {f"cv_{k}": v for k, v in metrics.items()}


def execute_run(
    spec: RunSpec,
    split: SplitData,
    context: RunContext,
    tracker: Tracker,
    *,
    run_name: str | None = None,
    cv_folds: int | None = None,
    evaluation_kind: str = STANDARD,
    extra_tags: dict[str, str] | None = None,
) -> RunResult:
    """Train one spec, evaluate it, and log everything. Selection never looks at test metrics.

    Cross-validated metrics (`cv_*`, out-of-fold on the training part) are for choosing between
    runs. The bare metrics (`accuracy` ... `roc_auc`) are computed once on the held-out test
    part, as the assignment compares them.
    """
    folds = context.cv_folds if cv_folds is None else cv_folds
    plan = make_column_plan(split.train, spec.extra_columns)
    leaked = set(plan.input_columns) - set(MODEL_INPUT_COLUMNS)
    if spec.leakage_status == "clean" and (
        leaked or set(plan.input_columns) & set(FORBIDDEN_MODEL_INPUTS)
    ):
        raise ValueError(f"{spec.name}: a clean run must not use {sorted(leaked)}")

    cols = list(plan.input_columns)
    X_train, y_train = split.train[cols], split.y_train
    X_test, y_test = split.test[cols], split.y_test
    pipeline = build_pipeline(plan, make_estimator(spec))

    cv = _cv_metrics(pipeline, X_train, y_train, folds, context.random_state, spec.threshold)
    pipeline.fit(X_train, y_train)
    scores = positive_scores(pipeline, X_test)
    test, y_pred = evaluate_scores(y_test, scores, spec.threshold)

    tags = {
        "leakage_status": spec.leakage_status,
        "known_defect": spec.known_defect or "none",
        "model_family": spec.model_family,
        "evaluation_kind": evaluation_kind,
        "selection_candidate": str(
            evaluation_kind == STANDARD and spec.leakage_status == "clean"
            and spec.model_family != "dummy"
        ).lower(),
        "dataset_version": context.dataset_version,
        "dataset_file": context.dataset_file,
        "dataset_sha256": context.dataset_sha256,
        "dataset_csv_sha256": context.dataset_csv_sha256,
        "cutoff_date": context.cutoff_date,
        "label_threshold": str(context.label_threshold),
        "git_commit": context.git_commit,
        "git_dirty": context.git_dirty,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "python_version": platform.python_version(),
        "random_state": str(context.random_state),
        "description": spec.description,
        **(extra_tags or {}),
    }
    summary = split.summary()
    params = {
        **spec.params,
        "threshold": spec.threshold,
        "random_state": context.random_state,
        "test_size": context.test_size,
        "cv_folds": folds,
        "n_input_columns": len(plan.input_columns),
        "excluded_constant_columns": ",".join(plan.excluded_constant) or "none",
        **summary,
    }
    metrics = {**test, **cv}

    name = run_name or spec.name
    with tracker.start_run(name) as run:
        run.set_tags(tags)
        run.log_params(params)
        run.log_metrics({k: v for k, v in metrics.items() if v == v})  # NaN is not logged
        run.log_confusion_matrix(
            confusion(y_test, y_pred), ["not_high_demand_proxy", "high_demand_proxy"],
            "confusion_matrix.png",
        )
        run.log_dict(report_dict(y_test, y_pred), "classification_report.json")
        run.log_dict(plan.as_dict(), "feature_columns.json")
        run.log_dict(context.dataset_metadata, "dataset_metadata_snapshot.json")
        # Integer columns cannot hold missing values, so the logged example uses floats.
        example = X_train.head(5)
        example = example.astype({c: "float64" for c in example.select_dtypes("integer").columns})
        run.log_model(pipeline, example)
        run_id = run.run_id

    assert all(m in test for m in METRIC_NAMES)
    return RunResult(run_id, name, tags, params, metrics, plan.as_dict(), summary)
