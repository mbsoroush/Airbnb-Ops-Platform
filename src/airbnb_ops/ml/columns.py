"""Which columns the model uses and how they are treated (pure, no scikit-learn)."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..features.config import (
    BOOLEAN_COLUMNS,
    CATEGORICAL_COLUMNS,
    LOG1P_COLUMNS,
    MODEL_INPUT_COLUMNS,
    NUMERIC_COLUMNS,
)


@dataclass(frozen=True)
class ColumnPlan:
    """The columns fed to the pipeline and how each group is treated.

    `excluded_constant` columns stay in the input (the request contract does not change) but
    the model ignores them. `leakage_columns` is only non-empty for the deliberately leaky run.
    """

    input_columns: tuple[str, ...]
    categorical: tuple[str, ...]
    boolean: tuple[str, ...]
    log_numeric: tuple[str, ...]
    numeric: tuple[str, ...]
    excluded_constant: tuple[str, ...]
    leakage_columns: tuple[str, ...]

    @property
    def used_columns(self) -> tuple[str, ...]:
        return self.categorical + self.boolean + self.log_numeric + self.numeric

    def as_dict(self) -> dict:
        return {
            "input_columns": list(self.input_columns),
            "used_columns": list(self.used_columns),
            "categorical_columns": list(self.categorical),
            "boolean_columns": list(self.boolean),
            "log1p_columns": list(self.log_numeric),
            "numeric_columns": list(self.numeric),
            "excluded_constant_columns": list(self.excluded_constant),
            "leakage_columns_included": list(self.leakage_columns),
        }


def make_column_plan(train: pd.DataFrame, extra_numeric: Sequence[str] = ()) -> ColumnPlan:
    """Decide the column treatment from the training data only.

    A column that is constant in the training data (including all-missing) carries no
    information and is excluded from the model.
    """
    extras = tuple(extra_numeric)
    inputs = tuple(MODEL_INPUT_COLUMNS) + extras

    def constant(col: str) -> bool:
        return train[col].nunique(dropna=False) <= 1

    excluded = tuple(c for c in inputs if constant(c))
    log_set = set(LOG1P_COLUMNS)
    return ColumnPlan(
        input_columns=inputs,
        categorical=tuple(c for c in CATEGORICAL_COLUMNS if c not in excluded),
        boolean=tuple(c for c in BOOLEAN_COLUMNS if c not in excluded),
        log_numeric=tuple(c for c in LOG1P_COLUMNS if c not in excluded),
        numeric=tuple(
            c for c in tuple(NUMERIC_COLUMNS) + extras if c not in log_set and c not in excluded
        ),
        excluded_constant=excluded,
        leakage_columns=extras,
    )


def _flag(series: pd.Series) -> pd.Series:
    """True/False/None/NaN -> 1.0/0.0/NaN."""
    return series.map(lambda v: np.nan if pd.isna(v) else float(bool(v))).astype("float64")


def normalize_input_frame(
    X: pd.DataFrame,
    numeric: Sequence[str],
    boolean: Sequence[str],
    categorical: Sequence[str],
) -> pd.DataFrame:
    """First step of the pipeline: one dtype per column group, missing values as NaN.

    It runs inside the fitted pipeline, so training and serving apply identical casting: JSON
    nulls (None), Python bools and numpy types all end up as float / object with NaN.
    """
    out = X.copy()
    for col in numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    for col in boolean:
        out[col] = _flag(out[col])
    for col in categorical:
        values = out[col].astype("object")
        out[col] = values.where(values.notna(), np.nan)
    return out
