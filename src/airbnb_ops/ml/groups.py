"""Group labels for the grouped comparisons. They are never logged or written to a file."""
from __future__ import annotations

import pandas as pd

from ..features.config import ENTITY_COLUMN
from ..sqlfiles import load_sql


def load_host_groups(reader) -> pd.Series:
    """listing_id -> integer host group, from a read-only query (host_key never leaves SQL)."""
    frame = reader.read_frame(load_sql("20_host_groups.sql"))
    return pd.Series(frame["host_group"].to_numpy(), index=frame[ENTITY_COLUMN].to_numpy())


def neighbourhood_groups(feature_frame: pd.DataFrame) -> pd.Series:
    """listing_id -> neighbourhood, taken from the feature table itself."""
    return pd.Series(
        feature_frame["neighbourhood_name"].to_numpy(),
        index=feature_frame[ENTITY_COLUMN].to_numpy(),
    )
