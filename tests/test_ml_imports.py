"""Only mlflow_tracker.py may import MLflow; no ML module may touch the database layer."""
import ast
from pathlib import Path

import airbnb_ops.ml as ml_pkg


def _imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_tracker_adapter_imports_mlflow():
    files = sorted(Path(ml_pkg.__file__).parent.glob("*.py"))
    assert len(files) >= 14
    for path in files:
        roots = _imported_roots(path)
        if path.name == "mlflow_tracker.py":
            continue
        assert "mlflow" not in roots, path.name
        assert not roots & {"sqlalchemy", "psycopg2", "fastapi", "airflow"}, path.name


def test_the_tracker_adapter_imports_mlflow_only_inside_functions():
    path = Path(ml_pkg.__file__).parent / "mlflow_tracker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top_level = {
        a.name.split(".")[0]
        for node in tree.body if isinstance(node, ast.Import) for a in node.names
    }
    assert "mlflow" not in top_level  # importing the module must work without MLflow installed
