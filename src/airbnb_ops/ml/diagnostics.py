"""Small diagnostics for the write-up: how informative is each feature on its own?"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ..features.config import TARGET_COLUMN


def univariate_auc(train: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    """ROC AUC of each numeric column on its own (missing values filled with the median).

    Values are folded to [0.5, 1]: 0.5 means no signal, 1.0 a perfect single-feature ranking.
    """
    y = train[TARGET_COLUMN]
    out: dict[str, float] = {}
    for col in columns:
        values = pd.to_numeric(train[col], errors="coerce")
        values = values.fillna(values.median())
        if values.nunique() < 2 or y.nunique() < 2 or np.isnan(values).all():
            out[col] = 0.5
            continue
        auc = float(roc_auc_score(y, values))
        out[col] = max(auc, 1 - auc)
    return out
