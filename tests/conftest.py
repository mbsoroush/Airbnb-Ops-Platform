import os
from dataclasses import replace
from pathlib import Path

import pytest

try:  # the ML tests need the optional `ml` extra
    import sklearn  # noqa: F401
except ImportError:
    collect_ignore_glob = ["test_ml_*.py", "test_mlflow_tracker.py"]
else:
    try:
        import mlflow  # noqa: F401
    except ImportError:
        collect_ignore_glob = ["test_mlflow_tracker.py"]

FIXTURES = Path(__file__).parent / "fixtures" / "mini_city"
FIXTURES_ML = Path(__file__).parent / "fixtures" / "mini_city_ml"
TEST_DB = os.getenv("AIRBNB_TEST_DB_NAME", "airbnb_test")
TEST_DB_ML = os.getenv("AIRBNB_TEST_ML_DB_NAME", "airbnb_test_ml")


@pytest.fixture(scope="session")
def mini_city() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def mini_city_ml() -> Path:
    """Synthetic city with a 140 day calendar (see tests/fixtures/make_mini_city_ml.py)."""
    return FIXTURES_ML


def _open_test_db(name: str):
    """A Database pointing at a separate test database (never the main one)."""
    if not os.getenv("AIRBNB_DB_HOST"):
        pytest.skip("AIRBNB_DB_HOST not set")

    from sqlalchemy import create_engine, text

    from airbnb_ops.db import Database
    from airbnb_ops.settings import DbSettings

    base = DbSettings.from_env()
    assert name != base.name, "test database must differ from the main database"

    admin = create_engine(replace(base, name="postgres").url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("select 1 from pg_database where datname = :n"), {"n": name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return Database(replace(base, name=name))


@pytest.fixture(scope="session")
def test_db():
    """Separate test database. Skips when AIRBNB_DB_HOST is not set (no Postgres needed)."""
    return _open_test_db(TEST_DB)


@pytest.fixture(scope="session")
def loaded_db(test_db, mini_city):
    """Test database with the mini fixture loaded into the core schema."""
    from airbnb_ops.ingest.load import load_city

    load_city(test_db, mini_city, salt="test-salt")
    return test_db


@pytest.fixture(scope="session")
def loaded_ml_db(mini_city_ml):
    """A second test database (airbnb_test_ml) holding the longer-calendar fixture.

    It is separate from airbnb_test so loading it can never change the data that the
    the earlier tests rely on.
    """
    db = _open_test_db(TEST_DB_ML)  # skips first when no Postgres is configured

    from airbnb_ops.ingest.load import load_city

    load_city(db, mini_city_ml, salt="test-salt")
    return db
