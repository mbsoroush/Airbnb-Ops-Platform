"""The experiment plan: one RunSpec per run. The same helper runs all of them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

LEAKAGE_COLUMN = "future_available_rate_30d"
LEAKAGE_DEFECT = "uses future_available_rate_30d"


@dataclass(frozen=True)
class RunSpec:
    name: str
    model_family: str  # dummy | logistic_regression | random_forest
    leakage_status: str  # clean | leaky
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    threshold: float = 0.50
    extra_columns: tuple[str, ...] = ()
    known_defect: str | None = None


def make_estimator(spec: RunSpec):
    if spec.model_family == "dummy":
        return DummyClassifier(**spec.params)
    if spec.model_family == "logistic_regression":
        return LogisticRegression(**spec.params)
    if spec.model_family == "random_forest":
        return RandomForestClassifier(n_jobs=-1, **spec.params)
    raise ValueError(f"unknown model family {spec.model_family!r}")


def default_run_specs(random_state: int = 42) -> list[RunSpec]:
    """Run 0 is leaky on purpose; run 1 is the dummy baseline; the rest are clean models.

    Threshold 0.50 of the balanced logistic regression is v3 itself; v4 covers the others.
    """
    lr = {"max_iter": 2000, "random_state": random_state, "class_weight": None}
    lr_balanced = {**lr, "class_weight": "balanced"}
    specs = [
        RunSpec(
            "v0_leaky_logistic_regression", "logistic_regression", "leaky",
            "Logistic regression that is given future_available_rate_30d, the quantity the "
            "label is made from. Wrong on purpose, to show what leakage looks like.",
            lr, extra_columns=(LEAKAGE_COLUMN,), known_defect=LEAKAGE_DEFECT,
        ),
        RunSpec(
            "v1_dummy_baseline", "dummy", "clean",
            "Always predicts the most frequent class: what a useless model scores.",
            {"strategy": "most_frequent"},
        ),
        RunSpec(
            "v2_clean_logistic_regression", "logistic_regression", "clean",
            "Logistic regression on the 26 contract columns.", lr,
        ),
        RunSpec(
            "v3_balanced_logistic_regression", "logistic_regression", "clean",
            "Logistic regression with class_weight=balanced (decision threshold 0.50).",
            lr_balanced,
        ),
    ]
    for threshold in (0.30, 0.40, 0.60):
        specs.append(
            RunSpec(
                f"v4_threshold_{threshold:.2f}", "logistic_regression", "clean",
                f"Balanced logistic regression with decision threshold {threshold:.2f}.",
                lr_balanced, threshold=threshold,
            )
        )
    specs += [
        RunSpec(
            "v5_random_forest", "random_forest", "clean",
            "Random forest, moderately deep.",
            {"n_estimators": 300, "max_depth": 12, "min_samples_leaf": 5,
             "class_weight": "balanced", "random_state": random_state},
        ),
        RunSpec(
            "v5b_random_forest_shallow", "random_forest", "clean",
            "Smaller, more regularised random forest.",
            {"n_estimators": 200, "max_depth": 6, "min_samples_leaf": 20,
             "class_weight": "balanced", "random_state": random_state},
        ),
    ]
    return specs
