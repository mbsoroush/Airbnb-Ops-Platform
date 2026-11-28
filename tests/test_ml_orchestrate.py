import pytest

from airbnb_ops.ml.orchestrate import SELECTION_TAGS, run_experiments
from airbnb_ops.ml.report import comparison_table, final_explanation, render_report
from airbnb_ops.ml.tracking import InMemoryTracker
from ml_synthetic import make_host_groups, make_loaded_dataset


@pytest.fixture(scope="module")
def outcome():
    dataset = make_loaded_dataset()
    tracker = InMemoryTracker()
    out = run_experiments(
        dataset, tracker, cv_folds=3, host_groups=make_host_groups(dataset.frame),
        robustness=make_loaded_dataset(version="v2"),
    )
    return out, tracker, dataset


def test_the_plan_meets_the_assignment_minimums(outcome):
    out, _, _ = outcome
    names = [r.name for r in out.results]
    assert len(out.results) >= 5
    assert {r.tags["leakage_status"] for r in out.results} == {"leaky", "clean"}
    assert {"dummy", "logistic_regression", "random_forest"} <= {
        r.tags["model_family"] for r in out.results}
    assert names[0] == "v0_leaky_logistic_regression" and "v1_dummy_baseline" in names
    assert {0.30, 0.40, 0.60} <= {r.params["threshold"] for r in out.results}


def test_exactly_one_clean_run_is_tagged_for_serving(outcome):
    out, tracker, _ = outcome
    tagged = [r for r in tracker.runs if r.tags.get("selected_for_serving") == "true"]
    assert len(tagged) == 1 and tagged[0].run_id == out.selection.run_id
    assert tagged[0].tags["production_candidate"] == "true"
    assert tagged[0].tags["leakage_status"] == "clean"
    assert set(SELECTION_TAGS) == {"selected_for_serving", "production_candidate"}


def test_rerunning_moves_the_selection_instead_of_adding_a_second_one(outcome):
    out, tracker, dataset = outcome
    second = run_experiments(dataset, tracker, cv_folds=3)
    tagged = [r for r in tracker.runs if r.tags.get("selected_for_serving") == "true"]
    assert [r.run_id for r in tagged] == [second.selection.run_id]


def test_extra_comparisons_are_diagnostics_not_candidates(outcome):
    out, tracker, _ = outcome
    kinds = {r.tags["evaluation_kind"] for r in out.extra_results}
    assert kinds == {"host_grouped", "neighbourhood_grouped", "cross_version_v2"}
    assert all(r.tags["selection_candidate"] == "false" for r in out.extra_results)
    assert all("cv_f1" not in r.metrics for r in out.extra_results)
    assert out.selection.run_id not in {r.run_id for r in out.extra_results}


def test_group_labels_never_reach_the_tracker(outcome):
    _, tracker, _ = outcome
    for run in tracker.runs:
        blob = str(run.dicts) + str(run.params) + str(run.tags)
        assert "host_group" not in blob.replace("host_grouped", "")
        assert all("group" not in name or name.endswith(".png") for name in run.artifact_names)


def test_host_grouped_comparison_is_skipped_without_groups(outcome):
    _, _, dataset = outcome
    out = run_experiments(dataset, InMemoryTracker(), cv_folds=3)
    assert any(s.startswith("host_grouped") for s in out.skipped)
    assert {r.tags["evaluation_kind"] for r in out.extra_results} == {"neighbourhood_grouped"}


def test_the_comparison_table_and_report(outcome):
    out, _, _ = outcome
    table = comparison_table(out.results)
    assert {"run_name", "f1", "roc_auc", "cv_f1", "leakage_status"} <= set(table.columns)
    text = render_report(out, experiment_name="exp", tracking_uri="http://x:5001")
    for needle in ("## Comparison", "## Selected run", "## Final explanation", "## Decisions",
                   "## Extra comparisons", "## How to read these scores", out.selection.run_id,
                   "instant_bookable", "log1p", "days_since_last_review", "v0_leaky"):
        assert needle in text
    assert "not independent evidence" in text and "never logged" in text


def test_the_explanation_names_the_selection_the_rejection_and_the_next_step(outcome):
    out, _, _ = outcome
    text = final_explanation(out)
    assert out.selection.run_name in text and "future_available_rate_30d" in text
    assert "temporal split" in text and "dummy" in text


def test_a_dry_run_report_says_nothing_was_sent_to_mlflow(outcome):
    out, _, _ = outcome
    text = render_report(out, experiment_name="e", tracking_uri="u", dry_run=True)
    assert "DRY RUN" in text and "not tagged anywhere" in text
