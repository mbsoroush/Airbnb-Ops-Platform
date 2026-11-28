"""Load a versioned feature dataset and verify it against its metadata."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..features.artifacts import artifact_paths, pyarrow_available, sha256_file
from ..features.config import TABLE_COLUMNS


class DatasetIntegrityError(RuntimeError):
    """The dataset file does not match the hash recorded in its metadata."""


@dataclass(frozen=True)
class LoadedDataset:
    frame: pd.DataFrame
    metadata: dict
    version: str
    source_file: str
    sha256: str
    csv_sha256: str


def load_dataset(features_dir: Path, version: str) -> LoadedDataset:
    """Read the dataset (Parquet when available, else CSV) and check its sha256 and columns."""
    paths = artifact_paths(Path(features_dir), version)
    if not paths["metadata"].exists():
        raise FileNotFoundError(
            f"{paths['metadata']} not found. Build it first: "
            f"airbnb-ops build-features --version {version}"
        )
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    files = metadata["files"]
    csv_sha = files["csv"]["sha256"]
    parquet_info = files.get("parquet")

    use_parquet = bool(parquet_info) and paths["parquet"].exists() and pyarrow_available()
    source = paths["parquet"] if use_parquet else paths["csv"]
    expected = parquet_info["sha256"] if use_parquet else csv_sha
    actual = sha256_file(source)
    if actual != expected:
        raise DatasetIntegrityError(
            f"{source.name} has sha256 {actual[:12]}, but its metadata recorded {expected[:12]}. "
            "The file changed after it was built; rebuild it or restore the original."
        )

    frame = pd.read_parquet(source) if use_parquet else pd.read_csv(source)
    if list(frame.columns) != list(TABLE_COLUMNS):
        raise ValueError(f"{source.name} does not follow the column contract")
    return LoadedDataset(
        frame=frame,
        metadata=metadata,
        version=version,
        source_file=source.name,
        sha256=actual,
        csv_sha256=csv_sha,
    )
