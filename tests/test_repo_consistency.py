"""Guards for decisions that live in several files, so they cannot drift apart."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_make_and_dvc_build_v2_with_the_same_command():
    make = re.search(r"^\tairbnb-ops build-features --version v2.*$", _read("Makefile"), re.M)
    dvc = re.search(r"cmd: (airbnb-ops build-features --version v2.*)$", _read("dvc.yaml"), re.M)
    assert make and dvc
    assert make.group(0).strip() == dvc.group(1).strip() == "airbnb-ops build-features --version v2"
    assert "--cutoff" not in _read("Makefile") and "--cutoff" not in _read("dvc.yaml")


def test_only_committed_reports_are_uncached_dvc_outputs():
    text = _read("dvc.yaml")
    uncached = re.findall(r"- (\S+):\n\s+cache: false", text)
    assert uncached and all(path.startswith("reports/") for path in uncached)
    for name in ("metadata.json", "validation_report.json", "pii_audit"):
        assert name in text
    assert not re.search(r"(metadata\.json|validation_report\.json|pii_audit_v\d\.csv):\n\s+cache",
                         text)


def test_readme_status_table_lists_six_numbered_stages():
    rows = re.findall(r"^\| (\d)\. ([^|]+?) \|", _read("README.md"), re.M)
    assert [(n, name) for n, name in rows] == [
        ("1", "Ingestion"), ("2", "Analytics and BI"), ("3", "Orchestration"),
        ("4", "Feature dataset"), ("5", "Experiment tracking"), ("6", "Model serving"),
    ]


def test_no_course_wording_in_visible_files():
    pattern = re.compile(r"\b(HW\s?\d+\w*|exercise)\b", re.IGNORECASE)
    files = [ROOT / n for n in ("README.md", "Makefile", "docker-compose.yml", ".env.example",
                                "dvc.yaml", "Dockerfile", "Dockerfile.mlflow", "pyproject.toml")]
    files += sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "src").rglob("*.sql"))
    files += sorted((ROOT / "reports").glob("*.md")) + sorted((ROOT / "dags").glob("*.py"))
    offenders = [f.name for f in files if pattern.search(f.read_text(encoding="utf-8"))]
    assert not offenders, offenders
    assert not (ROOT / "reports" / "hw01_a_run_report.md").exists()


def test_mlflow_versions_match_and_the_port_avoids_airplay():
    pin = re.search(r'"mlflow==([\d.]+)"', _read("pyproject.toml")).group(1)
    assert re.search(rf"ARG MLFLOW_VERSION={re.escape(pin)}", _read("Dockerfile.mlflow"))
    compose = _read("docker-compose.yml")
    assert f"MLFLOW_VERSION:-{pin}" in compose
    assert "${MLFLOW_HOST_PORT:-5001}:5000" in compose
    assert "--serve-artifacts" in compose and "mlflow-artifacts:/" in compose
    assert "MLFLOW_HOST_PORT" in _read(".env.example")


def test_sqlalchemy_is_pinned_below_2_1_for_mlflow_in_the_image_and_the_extra():
    dockerfile = _read("Dockerfile.mlflow")
    assert '"sqlalchemy>=2.0,<2.1"' in dockerfile
    assert '"sqlalchemy>=2.0,<2.1"' in _read("pyproject.toml")


def test_generated_and_local_ml_files_are_ignored_by_git():
    ignore = _read(".gitignore").splitlines()
    for entry in ("mlruns/", "mlartifacts/", "models/", "outputs/", "*.joblib", "*.pkl",
                  "host_groups*"):
        assert entry in ignore


def test_the_ml_extra_pins_scikit_learn_and_mlflow():
    text = _read("pyproject.toml")
    assert re.search(r'"scikit-learn==[\d.]+"', text) and re.search(r'"mlflow==[\d.]+"', text)
    assert "ml = [" in text
