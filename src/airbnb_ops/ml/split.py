"""Train/test splits: the standard stratified one and the grouped comparisons."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from ..features.config import ENTITY_COLUMN, TARGET_COLUMN

TEST_SIZE = 0.20
RANDOM_STATE = 42


@dataclass(frozen=True)
class SplitData:
    train: pd.DataFrame
    test: pd.DataFrame
    kind: str
    details: dict

    @property
    def y_train(self) -> pd.Series:
        return self.train[TARGET_COLUMN]

    @property
    def y_test(self) -> pd.Series:
        return self.test[TARGET_COLUMN]

    def summary(self) -> dict:
        return {
            "split_kind": self.kind,
            "n_train": len(self.train),
            "n_test": len(self.test),
            "train_positive_rate": round(float(self.y_train.mean()), 4),
            "test_positive_rate": round(float(self.y_test.mean()), 4),
            **self.details,
        }


def _check_both_classes(train: pd.DataFrame, test: pd.DataFrame, kind: str) -> None:
    for name, part in (("train", train), ("test", test)):
        if part[TARGET_COLUMN].nunique() < 2:
            raise ValueError(f"{kind}: the {name} part has only one class")


def stratified_split(
    frame: pd.DataFrame, test_size: float = TEST_SIZE, random_state: int = RANDOM_STATE
) -> SplitData:
    train, test = train_test_split(
        frame, test_size=test_size, random_state=random_state, stratify=frame[TARGET_COLUMN]
    )
    return SplitData(train.reset_index(drop=True), test.reset_index(drop=True), "random_split", {})


def grouped_split(
    frame: pd.DataFrame,
    groups: pd.Series,
    kind: str,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
) -> SplitData:
    """Hold out whole groups (for example all listings of a host).

    `groups` is indexed by listing_id. Listings without a group are dropped and counted.
    """
    labelled = frame.assign(_group=frame[ENTITY_COLUMN].map(groups))
    n_missing = int(labelled["_group"].isna().sum())
    labelled = labelled.dropna(subset=["_group"]).reset_index(drop=True)
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(splitter.split(labelled, groups=labelled["_group"]))
    train, test = labelled.iloc[train_idx], labelled.iloc[test_idx]
    overlap = set(train["_group"]) & set(test["_group"])
    if overlap:  # cannot happen with GroupShuffleSplit; guards against future changes
        raise RuntimeError(f"{kind}: groups appear in both train and test")
    _check_both_classes(train, test, kind)
    details = {
        "n_groups_train": int(train["_group"].nunique()),
        "n_groups_test": int(test["_group"].nunique()),
        "rows_without_group": n_missing,
    }
    return SplitData(
        train.drop(columns="_group").reset_index(drop=True),
        test.drop(columns="_group").reset_index(drop=True),
        kind,
        details,
    )


def cross_version_split(train_split: SplitData, other: pd.DataFrame, other_version: str):
    """Train on this split's training rows, evaluate on every row of another dataset version.

    Both versions contain the same listings, so this is a robustness check, not independent
    evidence.
    """
    _check_both_classes(train_split.train, other, f"cross_version_{other_version}")
    return SplitData(
        train_split.train, other.reset_index(drop=True), f"cross_version_{other_version}",
        {"other_version": other_version},
    )
