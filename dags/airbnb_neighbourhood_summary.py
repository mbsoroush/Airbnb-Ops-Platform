"""Airbnb neighbourhood summary: refresh the materialized view, validate it, write a report.

    read_config -> refresh_summary -> validate_summary -> choose_report_path
                                                           |-> write_success_report
                                                           |-> write_failure_report (then fails)

The logic lives in `airbnb_ops.pipeline` and is unit-tested without Airflow; this file only
wires it into tasks. Nothing secret is hard-coded:

* The warehouse comes from the Airflow Connection `airbnb_warehouse`
  (in docker-compose it is injected as the env var AIRFLOW_CONN_AIRBNB_WAREHOUSE).
* Tunables come from optional Airflow Variables:
  `airbnb_reports_dir` (default reports/airflow_runs),
  `airbnb_price_outlier_threshold` (default 5000),
  `airbnb_max_null_price_share` (default 0.5).

Trigger with `{"rebuild": true}` to drop and recreate the view instead of refreshing it
(needed after changing the view's SQL).
"""
import logging
from datetime import datetime, timedelta
from typing import Any

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import BaseHook, Param, Variable, dag, get_current_context, task

from airbnb_ops import pipeline

log = logging.getLogger(__name__)

DAG_ID = "airbnb_neighbourhood_summary"
CONN_ID = "airbnb_warehouse"


class HookRunner:
    """Adapts an Airflow PostgresHook to the SqlRunner protocol used by airbnb_ops.pipeline."""

    def __init__(self, hook: PostgresHook) -> None:
        self._hook = hook

    def execute_script(self, sql: str) -> None:
        self._hook.run(sql, autocommit=True)

    def fetch_row(self, sql: str) -> dict[str, Any]:
        conn = self._hook.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [desc[0] for desc in cur.description]
                row = cur.fetchone()
            conn.rollback()
        finally:
            conn.close()
        if row is None:
            raise LookupError("query returned no rows")
        return dict(zip(columns, row, strict=True))


def _runner() -> HookRunner:
    return HookRunner(PostgresHook(postgres_conn_id=CONN_ID))


@dag(
    dag_id=DAG_ID,
    description="Refresh and validate analytics.mv_airbnb_neighbourhood_summary, then report.",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "airbnb-ops", "retries": 2, "retry_delay": timedelta(minutes=1)},
    params={
        "rebuild": Param(
            False,
            type="boolean",
            description="Drop and recreate the view instead of refreshing it.",
        )
    },
    tags=["airbnb", "analytics"],
    doc_md=__doc__,
)
def airbnb_neighbourhood_summary():
    @task
    def read_config() -> dict[str, Any]:
        conn = BaseHook.get_connection(CONN_ID)  # fails clearly if the connection is missing
        config = {
            "reports_dir": Variable.get("airbnb_reports_dir", default="reports/airflow_runs"),
            "price_outlier_threshold": float(
                Variable.get(
                    "airbnb_price_outlier_threshold",
                    default=pipeline.DEFAULT_PRICE_OUTLIER_THRESHOLD,
                )
            ),
            "max_null_price_share": float(
                Variable.get(
                    "airbnb_max_null_price_share", default=pipeline.DEFAULT_MAX_NULL_PRICE_SHARE
                )
            ),
            "warehouse": f"{conn.host}:{conn.port}/{conn.schema}",
        }
        log.info("Config: %s", config)
        return config

    @task
    def refresh_summary(config: dict[str, Any]) -> dict[str, Any]:
        rebuild = bool(get_current_context()["params"]["rebuild"])
        log.info("Refreshing view in %s (rebuild=%s)", config["warehouse"], rebuild)
        result = pipeline.refresh_summary(_runner(), rebuild=rebuild)
        log.info("Refresh result: %s", result)
        return result

    @task
    def validate_summary(config: dict[str, Any], refresh: dict[str, Any]) -> dict[str, Any]:
        # `refresh` is unused on purpose: taking it as an argument orders validation after it.
        validation = pipeline.validate_summary(
            _runner(), config["price_outlier_threshold"], config["max_null_price_share"]
        )
        for name, check in validation["checks"].items():
            log.info("check %s: %s", name, check)
        return validation

    @task.branch
    def choose_report_path(validation: dict[str, Any]) -> str:
        return pipeline.report_task_id(validation)

    @task(task_id=pipeline.SUCCESS_TASK_ID)
    def write_success_report(
        config: dict[str, Any], refresh: dict[str, Any], validation: dict[str, Any]
    ) -> str:
        path = pipeline.write_run_report(
            config["reports_dir"], "success", DAG_ID, get_current_context()["run_id"],
            refresh, validation, config["warehouse"],
        )
        log.info("Wrote %s", path)
        return str(path)

    @task(task_id=pipeline.FAILURE_TASK_ID, retries=0)  # retrying a report would not help
    def write_failure_report(
        config: dict[str, Any], refresh: dict[str, Any], validation: dict[str, Any]
    ) -> None:
        path = pipeline.write_run_report(
            config["reports_dir"], "failure", DAG_ID, get_current_context()["run_id"],
            refresh, validation, config["warehouse"],
        )
        raise ValueError(f"{pipeline.failure_message(validation)} (report: {path})")

    config = read_config()
    refresh = refresh_summary(config)
    validation = validate_summary(config, refresh)
    choose_report_path(validation) >> [
        write_success_report(config, refresh, validation),
        write_failure_report(config, refresh, validation),
    ]


airbnb_neighbourhood_summary()
