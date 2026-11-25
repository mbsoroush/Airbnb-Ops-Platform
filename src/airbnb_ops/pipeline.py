"""Framework-free pipeline steps: refresh, validate, report.

The Airflow DAG (dags/airbnb_neighbourhood_summary.py) is a thin wrapper around these
functions, so the logic is unit-tested without Airflow. They need only the tiny SqlRunner
protocol below, which `airbnb_ops.db.Database` (local use) and an Airflow PostgresHook adapter
(in the DAG) both satisfy. This module imports neither pandas nor SQLAlchemy.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .constants import VIEW
from .sqlfiles import load_sql

SUCCESS_TASK_ID = "write_success_report"
FAILURE_TASK_ID = "write_failure_report"
DEFAULT_PRICE_OUTLIER_THRESHOLD = 5000.0
DEFAULT_MAX_NULL_PRICE_SHARE = 0.5


class SqlRunner(Protocol):
    def execute_script(self, sql: str) -> None: ...

    def fetch_row(self, sql: str) -> dict[str, Any]: ...


def refresh_summary(runner: SqlRunner, rebuild: bool = False) -> dict[str, Any]:
    """Create the view if missing, otherwise refresh it without blocking readers.

    `rebuild=True` drops and recreates it instead; use after changing the view's SQL, because
    REFRESH only recomputes the data, not the definition. Returns a small, JSON-safe dict.
    """
    started = time.perf_counter()
    present = bool(
        runner.fetch_row(f"SELECT to_regclass('{VIEW}') IS NOT NULL AS present")["present"]
    )
    if rebuild or not present:
        runner.execute_script(load_sql("02_create_materialized_view.sql"))
        action = "rebuilt" if present else "created"
    else:
        runner.execute_script(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {VIEW}")
        action = "refreshed"
    rows = int(runner.fetch_row(f"SELECT COUNT(*) AS n FROM {VIEW}")["n"])
    return {
        "action": action,
        "view": VIEW,
        "rows": rows,
        "seconds": round(time.perf_counter() - started, 2),
    }


def _check(value: Any, expected: str, passed: bool, severity: str = "error") -> dict[str, Any]:
    return {"value": value, "expected": expected, "passed": bool(passed), "severity": severity}


def validate_summary(
    runner: SqlRunner,
    price_outlier_threshold: float = DEFAULT_PRICE_OUTLIER_THRESHOLD,
    max_null_price_share: float = DEFAULT_MAX_NULL_PRICE_SHARE,
) -> dict[str, Any]:
    """Run the data-quality checks. Never raises on bad data: it reports pass/fail instead.

    "error" checks decide overall `passed`; "warn" checks are reported but do not fail the run.
    """
    threshold = float(price_outlier_threshold)
    sql = load_sql("03_validate_summary.sql").format(price_outlier_threshold=threshold)
    m = {key: int(value) for key, value in runner.fetch_row(sql).items()}
    listings = m["core_listings"]
    null_share = round(m["null_price_listings"] / listings, 4) if listings else 0.0

    checks = {
        "row_count": _check(m["row_count"], "> 0", m["row_count"] > 0),
        "null_neighbourhoods": _check(
            m["null_neighbourhoods"], "== 0", m["null_neighbourhoods"] == 0
        ),
        "bad_prices": _check(
            m["bad_prices"], "== 0 (negative avg or median)", m["bad_prices"] == 0
        ),
        "bad_availability": _check(
            m["bad_availability"], "== 0 (missing or outside 0..1)", m["bad_availability"] == 0
        ),
        "listing_reconciliation": _check(
            f"view {m['view_listings']} vs core {m['core_listings']}",
            "equal (view is not stale)",
            m["view_listings"] == m["core_listings"],
        ),
        "price_outliers": _check(
            m["price_outliers"], f"== 0 (price > {threshold:g})", m["price_outliers"] == 0, "warn"
        ),
        "null_price_share": _check(
            null_share, f"<= {max_null_price_share:g}", null_share <= max_null_price_share, "warn"
        ),
    }
    passed = all(c["passed"] for c in checks.values() if c["severity"] == "error")
    return {"passed": passed, "checks": checks}


def failed_error_checks(validation: dict[str, Any]) -> list[str]:
    return [
        name
        for name, check in validation["checks"].items()
        if check["severity"] == "error" and not check["passed"]
    ]


def report_task_id(validation: dict[str, Any]) -> str:
    """Branch decision: which report task should run."""
    return SUCCESS_TASK_ID if validation["passed"] else FAILURE_TASK_ID


def failure_message(validation: dict[str, Any]) -> str:
    return "Validation failed: " + ", ".join(failed_error_checks(validation))


def render_run_report(
    status: str,
    dag_id: str,
    run_id: str,
    refresh: dict[str, Any],
    validation: dict[str, Any],
    warehouse: str,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    lines = [
        f"# Airflow run report: {status.upper()}",
        "",
        f"- DAG: `{dag_id}`",
        f"- Run id: `{run_id}`",
        f"- Generated (UTC): {generated_at.isoformat(timespec='seconds')}",
        f"- Warehouse: `{warehouse}`",
        "",
        "## Refresh",
        "",
        "| Action | View | Rows | Seconds |",
        "| --- | --- | ---: | ---: |",
        f"| {refresh['action']} | `{refresh['view']}` | {refresh['rows']:,} "
        f"| {refresh['seconds']} |",
        "",
        "## Validation",
        "",
        "| Check | Value | Expected | Severity | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, check in validation["checks"].items():
        result = "pass" if check["passed"] else ("FAIL" if check["severity"] == "error" else "warn")
        lines.append(
            f"| {name} | {check['value']} | {check['expected']} | {check['severity']} | {result} |"
        )
    failed = failed_error_checks(validation)
    warned = [
        name
        for name, check in validation["checks"].items()
        if check["severity"] == "warn" and not check["passed"]
    ]
    lines += ["", f"**Overall: {'passed' if validation['passed'] else 'FAILED'}**"]
    if failed:
        lines.append(f"Failed checks: {', '.join(failed)}")
    if warned:
        lines.append(f"Warnings (do not fail the run): {', '.join(warned)}")
    return "\n".join(lines) + "\n"


def write_run_report(
    reports_dir: str | Path,
    status: str,
    dag_id: str,
    run_id: str,
    refresh: dict[str, Any],
    validation: dict[str, Any],
    warehouse: str,
) -> Path:
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    path = directory / f"{safe_run_id}__{status.lower()}.md"
    path.write_text(
        render_run_report(status, dag_id, run_id, refresh, validation, warehouse),
        encoding="utf-8",
    )
    return path
