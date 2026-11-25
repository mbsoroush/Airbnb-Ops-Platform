"""Pipeline logic (refresh, validate, report) with a fake SQL runner: no database, no Airflow."""
import json
import subprocess
import sys

import pytest

from airbnb_ops import pipeline
from airbnb_ops.constants import VIEW

GOOD_METRICS = {
    "row_count": 25,
    "null_neighbourhoods": 0,
    "bad_prices": 0,
    "bad_availability": 0,
    "view_listings": 7493,
    "core_listings": 7493,
    "null_price_listings": 2413,
    "price_outliers": 2,
}
REFRESH = {"action": "refreshed", "view": VIEW, "rows": 25, "seconds": 0.5}


class FakeRunner:
    def __init__(self, present=True, **metric_overrides):
        self.present = present
        self.metrics = {**GOOD_METRICS, **metric_overrides}
        self.scripts: list[str] = []
        self.queries: list[str] = []

    def execute_script(self, sql):
        self.scripts.append(sql)

    def fetch_row(self, sql):
        self.queries.append(sql)
        if "to_regclass" in sql:
            return {"present": self.present}
        if "COUNT(*) AS n" in sql:
            return {"n": 25}
        return dict(self.metrics)


def test_pipeline_imports_no_heavy_dependencies():
    """The Airflow container mounts src/ without installing pandas or SQLAlchemy for it."""
    code = (
        "import sys, airbnb_ops.pipeline;"
        "bad = {'pandas', 'sqlalchemy', 'typer'} & set(sys.modules);"
        "sys.exit(f'heavy imports: {bad}' if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_refresh_creates_the_view_when_missing():
    runner = FakeRunner(present=False)
    result = pipeline.refresh_summary(runner)
    assert result["action"] == "created" and result["rows"] == 25
    assert "CREATE MATERIALIZED VIEW" in runner.scripts[0]


def test_refresh_uses_concurrent_refresh_when_present():
    runner = FakeRunner(present=True)
    result = pipeline.refresh_summary(runner)
    assert result["action"] == "refreshed"
    assert runner.scripts == [f"REFRESH MATERIALIZED VIEW CONCURRENTLY {VIEW}"]


def test_rebuild_recreates_even_when_present():
    runner = FakeRunner(present=True)
    result = pipeline.refresh_summary(runner, rebuild=True)
    assert result["action"] == "rebuilt"
    assert "CREATE MATERIALIZED VIEW" in runner.scripts[0]


def test_good_data_passes_and_result_is_json_safe():
    validation = pipeline.validate_summary(FakeRunner())
    assert validation["passed"] is True
    assert set(validation["checks"]) >= {
        "row_count", "null_neighbourhoods", "bad_prices", "bad_availability",
    }
    json.dumps(validation)  # XCom must be able to serialize it
    json.dumps(pipeline.refresh_summary(FakeRunner()))


@pytest.mark.parametrize(
    ("override", "failing_check"),
    [
        ({"row_count": 0}, "row_count"),
        ({"null_neighbourhoods": 1}, "null_neighbourhoods"),
        ({"bad_prices": 3}, "bad_prices"),
        ({"bad_availability": 1}, "bad_availability"),
        ({"view_listings": 7000}, "listing_reconciliation"),
    ],
)
def test_each_error_check_fails_the_run(override, failing_check):
    validation = pipeline.validate_summary(FakeRunner(**override))
    assert validation["passed"] is False
    assert failing_check in pipeline.failed_error_checks(validation)
    assert pipeline.report_task_id(validation) == pipeline.FAILURE_TASK_ID
    assert failing_check in pipeline.failure_message(validation)


def test_warnings_are_reported_but_do_not_fail_the_run():
    validation = pipeline.validate_summary(
        FakeRunner(price_outliers=9, null_price_listings=6000), max_null_price_share=0.5
    )
    assert validation["passed"] is True
    assert validation["checks"]["price_outliers"]["passed"] is False
    assert validation["checks"]["null_price_share"]["passed"] is False
    assert pipeline.report_task_id(validation) == pipeline.SUCCESS_TASK_ID


def test_threshold_is_passed_into_the_sql_as_a_number():
    runner = FakeRunner()
    pipeline.validate_summary(runner, price_outlier_threshold=123)
    assert "price > 123.0" in runner.queries[0]


def test_no_listings_does_not_divide_by_zero():
    validation = pipeline.validate_summary(FakeRunner(core_listings=0, view_listings=0))
    assert validation["checks"]["null_price_share"]["value"] == 0.0


def test_report_lists_checks_and_failures():
    validation = pipeline.validate_summary(FakeRunner(bad_prices=2))
    text = pipeline.render_run_report(
        "failure", "dag_x", "run_1", REFRESH, validation, "postgres:5432/airbnb"
    )
    assert "FAILURE" in text and "dag_x" in text and "run_1" in text
    assert "Failed checks: bad_prices" in text
    assert "price_outliers" in text and "warn" in text


def test_report_file_name_is_filesystem_safe_and_has_no_secrets(tmp_path):
    validation = pipeline.validate_summary(FakeRunner())
    path = pipeline.write_run_report(
        tmp_path / "nested", "success", "dag_x", "scheduled__2026-11-25T03:00:00+00:00",
        REFRESH, validation, "postgres:5432/airbnb",
    )
    assert path.parent == tmp_path / "nested" and path.name.endswith("__success.md")
    assert ":" not in path.name and "+" not in path.name
    assert "password" not in path.read_text().lower()
