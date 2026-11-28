import pytest

from airbnb_ops.ml.run import RunResult
from airbnb_ops.ml.select import AUC_MARGIN, select_best_clean


def _result(name, *, family="logistic_regression", leaky=False, cv_f1, cv_auc, test_f1=0.5,
            test_auc=0.5):
    tags = {
        "leakage_status": "leaky" if leaky else "clean",
        "model_family": family,
        "selection_candidate": str(not leaky and family != "dummy").lower(),
        "evaluation_kind": "random_split",
    }
    metrics = {"cv_f1": cv_f1, "cv_roc_auc": cv_auc, "f1": test_f1, "roc_auc": test_auc}
    return RunResult(f"id-{name}", name, tags, {}, metrics, {})


DUMMY = _result("dummy", family="dummy", cv_f1=0.73, cv_auc=0.50)


def test_the_highest_roc_auc_wins_even_with_a_lower_f1():
    runs = [
        DUMMY,
        _result("high_f1", cv_f1=0.80, cv_auc=0.70),
        _result("high_auc", cv_f1=0.75, cv_auc=0.76),
    ]
    sel = select_best_clean(runs)
    assert sel.run_name == "high_auc" and sel.run_id == "id-high_auc" and sel.note is None
    assert sel.eligible == ["high_auc", "high_f1"]
    assert sel.baseline["cv_roc_auc"] == 0.50 and "ROC AUC" in sel.rule


def test_runs_within_a_tiny_auc_difference_are_tied_and_f1_breaks_the_tie():
    # the same model at three thresholds has an identical AUC; F1 chooses the threshold
    runs = [
        DUMMY,
        _result("thr_0.30", cv_f1=0.76, cv_auc=0.7500),
        _result("thr_0.40", cv_f1=0.78, cv_auc=0.7500),
        _result("thr_0.60", cv_f1=0.74, cv_auc=0.7500),
        _result("other_model", cv_f1=0.90, cv_auc=0.7480),  # 0.002 lower: not tied
    ]
    assert select_best_clean(runs).run_name == "thr_0.40"


def test_the_leaky_run_is_never_selected_however_good_it_looks():
    runs = [DUMMY, _result("leaky", leaky=True, cv_f1=0.99, cv_auc=0.99, test_f1=0.99),
            _result("clean", cv_f1=0.78, cv_auc=0.70)]
    assert select_best_clean(runs).run_name == "clean"


def test_test_metrics_do_not_influence_the_choice():
    runs = [
        DUMMY,
        _result("good_cv", cv_f1=0.78, cv_auc=0.72, test_f1=0.10, test_auc=0.10),
        _result("good_test", cv_f1=0.78, cv_auc=0.70, test_f1=0.99, test_auc=0.99),
    ]
    assert select_best_clean(runs).run_name == "good_cv"


def test_a_run_must_beat_the_dummy_by_the_margin_to_be_eligible():
    runs = [
        DUMMY,
        _result("barely_better", cv_f1=0.95, cv_auc=0.50 + AUC_MARGIN / 2),
        _result("clearly_better", cv_f1=0.70, cv_auc=0.50 + AUC_MARGIN),
    ]
    sel = select_best_clean(runs)
    assert sel.run_name == "clearly_better" and sel.eligible == ["clearly_better"]


def test_fallback_when_nothing_beats_the_dummy_is_flagged():
    runs = [DUMMY, _result("a", cv_f1=0.70, cv_auc=0.52), _result("b", cv_f1=0.71, cv_auc=0.51)]
    sel = select_best_clean(runs)
    assert sel.run_name == "a" and sel.eligible == []
    assert "no demonstrated skill" in sel.note


def test_remaining_ties_are_broken_by_name():
    runs = [DUMMY, _result("b", cv_f1=0.80, cv_auc=0.70), _result("a", cv_f1=0.80, cv_auc=0.70)]
    assert select_best_clean(runs).run_name == "b"


def test_selection_needs_the_baseline_and_a_candidate():
    with pytest.raises(ValueError, match="dummy"):
        select_best_clean([_result("a", cv_f1=0.8, cv_auc=0.7)])
    with pytest.raises(ValueError, match="no clean candidate"):
        select_best_clean([DUMMY])
