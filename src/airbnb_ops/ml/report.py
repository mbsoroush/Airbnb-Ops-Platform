"""Comparison table and the written explanation (pure; numbers come from the results)."""
from __future__ import annotations

import pandas as pd

from .orchestrate import ExperimentOutcome
from .run import RunResult

_TABLE_METRICS = ["accuracy", "precision", "recall", "f1", "roc_auc", "cv_f1", "cv_roc_auc"]


def comparison_table(results: list[RunResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        row = {
            "run_name": r.name,
            "leakage_status": r.tags["leakage_status"],
            "model_family": r.tags["model_family"],
            "evaluation": r.tags["evaluation_kind"],
            "threshold": r.params.get("threshold"),
        }
        row.update({m: round(r.metrics[m], 4) if m in r.metrics else None for m in _TABLE_METRICS})
        row["run_id"] = r.run_id
        rows.append(row)
    return pd.DataFrame(rows)


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if v is None or v != v else str(v) for v in row) + " |")
    return "\n".join(lines)


def _f(value, digits: int = 3) -> str:
    return "n/a" if value is None or value != value else f"{value:.{digits}f}"


def final_explanation(outcome: ExperimentOutcome) -> str:
    by_name = {r.name: r for r in outcome.results}
    sel = by_name[outcome.selection.run_name]
    leaky = next((r for r in outcome.results if r.tags["leakage_status"] == "leaky"), None)
    dummy = next(r for r in outcome.results if r.tags["model_family"] == "dummy")
    positive = outcome.split_summary["test_positive_rate"]
    parts = [
        f"I selected `{sel.name}` (run `{sel.run_id}`): its cross-validated ROC AUC is "
        f"{_f(sel.metrics['cv_roc_auc'])} and F1 {_f(sel.metrics['cv_f1'])}, against "
        f"{_f(dummy.metrics['cv_roc_auc'])} and {_f(dummy.metrics['cv_f1'])} for the dummy "
        f"baseline, and its single held-out test result is ROC AUC {_f(sel.metrics['roc_auc'])}, "
        f"F1 {_f(sel.metrics['f1'])}.",
        "It was chosen on cross-validated metrics of the training part only, uses clean "
        "features, and logs the full preprocessing pipeline.",
    ]
    if leaky is not None:
        parts.append(
            f"The leaky run `{leaky.name}` reaches ROC AUC {_f(leaky.metrics['roc_auc'])} on the "
            "test part because future_available_rate_30d is the quantity the label is made "
            "from, so it is rejected whatever its score."
        )
    parts.append(
        f"Because about {positive:.0%} of listings are positive, even the dummy gets F1 "
        f"{_f(dummy.metrics['f1'])}, which is why selection ranks by ROC AUC first and uses F1 "
        "only to break ties between thresholds of the same model."
    )
    parts.append(
        "Next I would test on a true temporal split built from several calendar snapshots and "
        "add features that are known before the cutoff."
    )
    return " ".join(parts)


def render_report(
    outcome: ExperimentOutcome, *, experiment_name: str, tracking_uri: str, dry_run: bool = False
) -> str:
    ctx, sel = outcome.context, outcome.selection
    chosen = next(r for r in outcome.results if r.name == sel.run_name)
    split = outcome.split_summary
    excluded = chosen.columns["excluded_constant_columns"]
    head = [
        f"# Experiment tracking: {experiment_name}",
        "",
        f"- Dataset: `{ctx.dataset_version}` (`{ctx.dataset_file}`, sha256 "
        f"`{ctx.dataset_sha256[:12]}`), cutoff {ctx.cutoff_date}",
        f"- Git commit: `{ctx.git_commit[:12]}` (dirty: {ctx.git_dirty})",
        f"- Tracking: {'DRY RUN (in memory, nothing sent to MLflow)' if dry_run else tracking_uri}",
        f"- Split: stratified, test_size {ctx.test_size}, random_state {ctx.random_state}; "
        f"{split['n_train']} train / {split['n_test']} test rows, positive rate "
        f"{split['train_positive_rate']} / {split['test_positive_rate']}",
        f"- Cross-validation: {ctx.cv_folds} stratified folds on the training part",
    ]
    sections = [
        "\n".join(head),
        "## Comparison\n\nBare metrics (`accuracy` ... `roc_auc`) are computed once on the "
        "held-out test part, as is conventional. `cv_*` metrics are out-of-fold "
        "on the training part and are the only ones used for selection.\n\n"
        + _md(comparison_table(outcome.results)),
        f"## Selected run\n\n- `{sel.run_name}` (run id `{sel.run_id}`), tagged "
        "`selected_for_serving=true` and `production_candidate=true`"
        + ("" if not dry_run else " (dry run: not tagged anywhere)")
        + f"\n- Rule: {sel.rule}\n- Eligible runs: "
        + (", ".join(f"`{n}`" for n in sel.eligible) or "none")
        + (f"\n- Note: {sel.note}" if sel.note else ""),
        "## Final explanation\n\n" + final_explanation(outcome),
        "## Decisions\n\n"
        f"- `instant_bookable` and any other constant column: excluded from the model "
        f"({', '.join(excluded) or 'none were constant'}). In the Munich file `instant_bookable` "
        "is empty, so after the fill rule it is constant False and carries no information. "
        "The request contract still contains it.\n"
        "- Price: `log1p` plus median imputation with a missing indicator, inside the Pipeline, so "
        "serving applies the identical transformation (about a third of prices are missing and "
        "the maximum is about 80,000 per night).\n"
        "- `days_since_last_review`: kept because the column contract is fixed. Univariate ROC AUC "
        "on the training part (0.5 = no signal): "
        + ", ".join(f"`{k}` {v:.3f}" for k, v in outcome.diagnostics.items())
        + ".",
    ]
    if outcome.extra_results:
        extra = comparison_table(outcome.extra_results).drop(columns=["cv_f1", "cv_roc_auc"])
        sections.append(
            "## Extra comparisons for the selected configuration\n\n"
            "These are diagnostics, not part of the selection. Grouped splits hold out whole "
            "hosts or neighbourhoods, so they show how much a random split flatters the score. "
            "The group labels stay in memory and are never logged. A cross-version check is not "
            "independent evidence: both dataset versions contain the same listings.\n\n"
            + _md(extra)
        )
    if outcome.skipped:
        sections.append("## Skipped\n\n" + "\n".join(f"- {s}" for s in outcome.skipped))
    sections.append(
        "## How to read these scores\n\n"
        "- The label is a low-availability proxy (booked or blocked by the host), not confirmed "
        "demand.\n"
        "- Features and label come from the same forward-looking calendar snapshot, so none of "
        "these numbers prove that the model predicts real bookings, and no split here is a true "
        "temporal split.\n"
        "- The positive class is the majority, so accuracy and F1 of a trivial model are high; "
        "compare ROC AUC and the dummy baseline."
    )
    return "\n\n".join(sections) + "\n"
