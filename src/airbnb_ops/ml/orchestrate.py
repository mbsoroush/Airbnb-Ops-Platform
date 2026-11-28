"""Run the whole experiment plan: standard runs, selection, then the extra comparisons."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .data import LoadedDataset
from .diagnostics import univariate_auc
from .groups import neighbourhood_groups
from .run import RunContext, RunResult, build_run_context, execute_run
from .select import Selection, select_best_clean
from .specs import RunSpec, default_run_specs
from .split import RANDOM_STATE, TEST_SIZE, cross_version_split, grouped_split, stratified_split
from .tracking import Tracker

SELECTION_TAGS = {"selected_for_serving": "true", "production_candidate": "true"}
DIAGNOSTIC_COLUMNS = [
    "days_since_last_review",
    "available_rate_last_30d",
    "available_rate_last_90d",
    "total_reviews_before_cutoff",
    "listing_price",
    "accommodates",
]


@dataclass(frozen=True)
class ExperimentOutcome:
    results: list[RunResult]
    selection: Selection
    extra_results: list[RunResult]
    skipped: list[str]
    diagnostics: dict[str, float]
    context: RunContext
    split_summary: dict = field(default_factory=dict)


def run_experiments(
    dataset: LoadedDataset,
    tracker: Tracker,
    *,
    specs: list[RunSpec] | None = None,
    cv_folds: int = 5,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
    host_groups: pd.Series | None = None,
    robustness: LoadedDataset | None = None,
) -> ExperimentOutcome:
    specs = specs if specs is not None else default_run_specs(random_state)
    split = stratified_split(dataset.frame, test_size, random_state)
    context = build_run_context(dataset, cv_folds, random_state, test_size)

    results = [execute_run(spec, split, context, tracker) for spec in specs]
    selection = select_best_clean(results)
    tracker.clear_tags(list(SELECTION_TAGS))
    tracker.set_run_tags(selection.run_id, SELECTION_TAGS)

    chosen = next(s for s in specs if s.name == selection.run_name)
    extra: list[RunResult] = []
    skipped: list[str] = []

    def extra_run(label: str, make_split, kind: str) -> None:
        try:
            part = make_split()
        except ValueError as exc:
            skipped.append(f"{label}: {exc}")
            return
        extra.append(
            execute_run(
                chosen, part, context, tracker,
                run_name=f"v6_{label}_{chosen.name}", cv_folds=0, evaluation_kind=kind,
            )
        )

    if host_groups is None:
        skipped.append("host_grouped: skipped (no host groups; they need the database)")
    else:
        extra_run(
            "host_grouped",
            lambda: grouped_split(dataset.frame, host_groups, "host_grouped", test_size,
                                  random_state),
            "host_grouped",
        )
    extra_run(
        "neighbourhood_grouped",
        lambda: grouped_split(dataset.frame, neighbourhood_groups(dataset.frame),
                              "neighbourhood_grouped", test_size, random_state),
        "neighbourhood_grouped",
    )
    if robustness is not None:
        extra_run(
            f"cross_version_{robustness.version}",
            lambda: cross_version_split(split, robustness.frame, robustness.version),
            f"cross_version_{robustness.version}",
        )

    return ExperimentOutcome(
        results=results,
        selection=selection,
        extra_results=extra,
        skipped=skipped,
        diagnostics=univariate_auc(split.train, DIAGNOSTIC_COLUMNS),
        context=context,
        split_summary=split.summary(),
    )
