"""Named dataset versions: one place for each version's cutoff and the reason for it.

`make features-v2`, the DVC stage and any other caller just pass `--version v2`, so every route
builds identical metadata (a dataset version is immutable).
"""
from __future__ import annotations

from datetime import date

from .config import FeatureConfig

DATASET_PRESETS: dict[str, dict] = {
    "v1": {},  # earliest valid cutoff, derived from the data
    "v2": {
        "cutoff_date": date(2027, 2, 22),
        "cutoff_reason": (
            "Avoids the Christmas and New Year label window of v1. Comparison dataset; the "
            "cutoff was not chosen by model score."
        ),
    },
}


def resolve_config(
    version: str,
    cutoff: date | None = None,
    cutoff_reason: str | None = None,
    threshold: float | None = None,
) -> FeatureConfig:
    """Build the FeatureConfig for a version. Explicit arguments override the preset."""
    preset = DATASET_PRESETS.get(version, {})
    kwargs = {
        "dataset_version": version,
        "cutoff_date": cutoff or preset.get("cutoff_date"),
        "cutoff_reason": cutoff_reason or (None if cutoff else preset.get("cutoff_reason")),
    }
    if threshold is not None:
        kwargs["label_threshold"] = threshold
    return FeatureConfig(**kwargs)
