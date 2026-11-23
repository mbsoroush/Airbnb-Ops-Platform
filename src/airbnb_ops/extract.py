"""Extraction helpers."""
from pathlib import Path

import pandas as pd


def read_csv_checked(path: Path) -> pd.DataFrame:
    """Read a CSV, raising FileNotFoundError with a clear message if missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    return pd.read_csv(path)
