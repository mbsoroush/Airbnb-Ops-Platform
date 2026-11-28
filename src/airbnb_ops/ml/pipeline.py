"""The sklearn Pipeline that is trained, logged and served (one object, one transformation)."""
from __future__ import annotations

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from .columns import ColumnPlan, normalize_input_frame


def build_pipeline(plan: ColumnPlan, estimator) -> Pipeline:
    """normalize -> ColumnTransformer -> model.

    Numeric: median imputation with a missing indicator, optional log1p, scaling. Booleans:
    cast to 0/1 then most frequent. Categorical: most frequent, one-hot with rare categories
    grouped. Unused (constant) columns are dropped by the ColumnTransformer.
    """
    log_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("log1p", FunctionTransformer(np.log1p)),
            ("scale", StandardScaler()),
        ]
    )
    numeric_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    boolean_pipe = Pipeline([("impute", SimpleImputer(strategy="most_frequent"))])
    categorical_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist", min_frequency=20, sparse_output=False
                ),
            ),
        ]
    )
    groups = [
        ("log_numeric", log_pipe, list(plan.log_numeric)),
        ("numeric", numeric_pipe, list(plan.numeric)),
        ("boolean", boolean_pipe, list(plan.boolean)),
        ("categorical", categorical_pipe, list(plan.categorical)),
    ]
    preprocess = ColumnTransformer(
        [(name, pipe, cols) for name, pipe, cols in groups if cols], remainder="drop"
    )
    normalize = FunctionTransformer(
        normalize_input_frame,
        kw_args={
            "numeric": list(plan.log_numeric + plan.numeric),
            "boolean": list(plan.boolean),
            "categorical": list(plan.categorical),
        },
    )
    return Pipeline([("normalize", normalize), ("preprocess", preprocess), ("model", estimator)])
