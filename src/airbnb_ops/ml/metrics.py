"""Metrics shared by every run: accuracy, precision, recall, f1, roc_auc."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

METRIC_NAMES = ("accuracy", "precision", "recall", "f1", "roc_auc")


def positive_scores(model, X) -> np.ndarray:
    """Probability of class 1, found through `classes_` (never a hard-coded column)."""
    classes = list(model.classes_)
    if 1 not in classes:
        return np.zeros(len(X))
    return model.predict_proba(X)[:, classes.index(1)]


def evaluate_scores(y_true, scores, threshold: float) -> tuple[dict[str, float], np.ndarray]:
    """Threshold the scores and compute the five metrics (zero_division=0)."""
    y_true = np.asarray(y_true)
    y_pred = (np.asarray(scores) >= threshold).astype(int)
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, scores)) if len(set(y_true)) == 2 else float("nan"),
    }
    return metrics, y_pred


def confusion(y_true, y_pred) -> list[list[int]]:
    """[[tn, fp], [fn, tp]]"""
    return confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist()


def report_dict(y_true, y_pred) -> dict:
    return classification_report(
        y_true, y_pred, labels=[0, 1], output_dict=True, zero_division=0
    )
