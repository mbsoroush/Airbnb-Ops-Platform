"""The features package must stay framework-free: no SQLAlchemy, no ML libraries."""
import ast
from pathlib import Path

import airbnb_ops.features as features_pkg

FORBIDDEN = {"sqlalchemy", "psycopg2", "sklearn", "mlflow", "fastapi", "airflow"}


def _imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_features_package_imports_no_database_or_ml_framework():
    files = sorted(Path(features_pkg.__file__).parent.glob("*.py"))
    assert len(files) >= 8
    for path in files:
        assert not _imported_roots(path) & FORBIDDEN, path.name
