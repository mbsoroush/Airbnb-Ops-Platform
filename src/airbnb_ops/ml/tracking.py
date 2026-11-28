"""The tracking boundary: a tiny protocol the run helper talks to, plus an in-memory fake.

Only mlflow_tracker.py imports MLflow. Tests and `--dry-run` use InMemoryTracker.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd


class RunHandle(Protocol):
    run_id: str

    def set_tags(self, tags: Mapping[str, str]) -> None: ...

    def log_params(self, params: Mapping[str, Any]) -> None: ...

    def log_metrics(self, metrics: Mapping[str, float]) -> None: ...

    def log_dict(self, payload: Mapping[str, Any], artifact_file: str) -> None: ...

    def log_confusion_matrix(
        self, matrix: Sequence[Sequence[int]], labels: Sequence[str], artifact_file: str
    ) -> None: ...

    def log_model(self, pipeline: Any, input_example: pd.DataFrame) -> None: ...


class Tracker(Protocol):
    def start_run(self, run_name: str) -> AbstractContextManager[RunHandle]: ...

    def set_run_tags(self, run_id: str, tags: Mapping[str, str]) -> None: ...

    def clear_tags(self, keys: Sequence[str]) -> int:
        """Remove these tags from every run of the experiment; returns how many runs changed."""
        ...


@dataclass
class RecordedRun:
    run_id: str
    name: str
    tags: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    dicts: dict[str, dict] = field(default_factory=dict)
    figures: dict[str, list] = field(default_factory=dict)
    models: list[Any] = field(default_factory=list)
    examples: list[pd.DataFrame] = field(default_factory=list)

    @property
    def artifact_names(self) -> list[str]:
        names = list(self.dicts) + list(self.figures)
        return names + (["model"] if self.models else [])


class _InMemoryHandle:
    def __init__(self, run: RecordedRun):
        self._run = run
        self.run_id = run.run_id

    def set_tags(self, tags: Mapping[str, str]) -> None:
        self._run.tags.update({k: str(v) for k, v in tags.items()})

    def log_params(self, params: Mapping[str, Any]) -> None:
        self._run.params.update(params)

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._run.metrics.update(metrics)

    def log_dict(self, payload: Mapping[str, Any], artifact_file: str) -> None:
        self._run.dicts[artifact_file] = dict(payload)

    def log_confusion_matrix(self, matrix, labels, artifact_file: str) -> None:
        self._run.figures[artifact_file] = [list(row) for row in matrix]

    def log_model(self, pipeline: Any, input_example: pd.DataFrame) -> None:
        self._run.models.append(pipeline)
        self._run.examples.append(input_example)


class InMemoryTracker:
    """Records everything in memory: for tests and for `experiments --dry-run`."""

    def __init__(self) -> None:
        self.runs: list[RecordedRun] = []

    @contextmanager
    def start_run(self, run_name: str) -> Iterator[RunHandle]:
        run = RecordedRun(run_id=f"mem-{len(self.runs) + 1:04d}", name=run_name)
        self.runs.append(run)
        yield _InMemoryHandle(run)

    def set_run_tags(self, run_id: str, tags: Mapping[str, str]) -> None:
        self.get(run_id).tags.update({k: str(v) for k, v in tags.items()})

    def clear_tags(self, keys: Sequence[str]) -> int:
        changed = 0
        for run in self.runs:
            removed = [k for k in keys if run.tags.pop(k, None) is not None]
            changed += bool(removed)
        return changed

    def get(self, run_id: str) -> RecordedRun:
        return next(r for r in self.runs if r.run_id == run_id)
