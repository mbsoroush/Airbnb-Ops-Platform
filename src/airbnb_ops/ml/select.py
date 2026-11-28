"""Choosing the final candidate (pure). Selection uses cross-validated metrics, not test."""
from __future__ import annotations

from dataclasses import dataclass, field

from .run import RunResult

AUC_MARGIN = 0.05
AUC_TIE = 0.001

RULE = (
    "Among clean, standard-split runs that are not the dummy baseline, keep those whose "
    f"cross-validated ROC AUC beats the dummy's by at least {AUC_MARGIN:.2f}, and take the "
    f"highest cross-validated ROC AUC. Runs within {AUC_TIE} of the best count as tied (for "
    "example the same model at different decision thresholds); ties go to the higher "
    "cross-validated F1, then to the name. ROC AUC comes first because the positive class is "
    "the majority: a dummy that always predicts it already scores a high F1, so F1 alone "
    "cannot show skill. The leaky run can never be selected, and test metrics are not used."
)


@dataclass(frozen=True)
class Selection:
    run_id: str
    run_name: str
    rule: str
    baseline: dict[str, float]
    eligible: list[str] = field(default_factory=list)
    note: str | None = None


def select_best_clean(results: list[RunResult]) -> Selection:
    dummy = next((r for r in results if r.tags.get("model_family") == "dummy"), None)
    if dummy is None or "cv_roc_auc" not in dummy.metrics:
        raise ValueError("selection needs the dummy baseline with cross-validated metrics")
    candidates = [r for r in results if r.tags.get("selection_candidate") == "true"]
    if not candidates:
        raise ValueError("no clean candidate runs to choose from")

    base_auc = dummy.metrics["cv_roc_auc"]
    eligible = [r for r in candidates if r.metrics["cv_roc_auc"] >= base_auc + AUC_MARGIN]
    pool = eligible or candidates
    note = None
    if not eligible:
        note = (
            f"No clean run beat the dummy baseline by {AUC_MARGIN:.2f} cross-validated ROC AUC; "
            "the run with the highest cross-validated ROC AUC was taken anyway. Treat this model "
            "as having no demonstrated skill."
        )
    top = max(r.metrics["cv_roc_auc"] for r in pool)
    contenders = [r for r in pool if r.metrics["cv_roc_auc"] >= top - AUC_TIE]
    best = max(contenders, key=lambda r: (r.metrics["cv_f1"], r.metrics["cv_roc_auc"], r.name))
    return Selection(
        run_id=best.run_id,
        run_name=best.name,
        rule=RULE,
        baseline={"cv_f1": dummy.metrics.get("cv_f1", float("nan")), "cv_roc_auc": base_auc},
        eligible=sorted(r.name for r in eligible),
        note=note,
    )
