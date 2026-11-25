"""DAG integrity: parses, has the intended shape, and hard-codes no credentials.

Skipped when Airflow is not installed (it is a heavy, separately pinned dependency).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="airflow_home_"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")

pytest.importorskip("airflow")

DAGS = Path(__file__).resolve().parents[1] / "dags"
DAG_ID = "airbnb_neighbourhood_summary"


@pytest.fixture(scope="module")
def dag_bag():
    # DagBag looks DAGs up in the metadata DB, so make sure its (SQLite) schema exists.
    airflow_cli = Path(sys.executable).with_name("airflow")
    subprocess.run([str(airflow_cli), "db", "migrate"], check=True, capture_output=True)
    from airflow.dag_processing.dagbag import DagBag

    return DagBag(dag_folder=str(DAGS), bundle_path=DAGS, bundle_name="airbnb-ops-tests")


@pytest.fixture(scope="module")
def dag(dag_bag):
    assert not dag_bag.import_errors, dag_bag.import_errors
    return dag_bag.get_dag(DAG_ID)


def test_dag_imports_cleanly_and_is_registered(dag_bag, dag):
    assert dag is not None and dag.dag_id == DAG_ID


def test_dag_has_the_intended_tasks_and_flow(dag):
    assert set(dag.task_ids) == {
        "read_config", "refresh_summary", "validate_summary", "choose_report_path",
        "write_success_report", "write_failure_report",
    }
    upstream = {task_id: dag.get_task(task_id).upstream_task_ids for task_id in dag.task_ids}
    assert upstream["read_config"] == set()
    assert upstream["refresh_summary"] == {"read_config"}
    assert upstream["validate_summary"] == {"read_config", "refresh_summary"}
    assert upstream["choose_report_path"] == {"validate_summary"}
    assert dag.get_task("choose_report_path").downstream_task_ids == {
        "write_success_report", "write_failure_report",
    }


def test_dag_settings_are_production_minded(dag):
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.get_task("write_failure_report").retries == 0
    assert dag.get_task("refresh_summary").retries >= 1


def test_dag_file_contains_no_credentials():
    source = (DAGS / "airbnb_neighbourhood_summary.py").read_text().lower()
    for forbidden in ("postgres://", "postgresql://", "password=", "passwd"):
        assert forbidden not in source
