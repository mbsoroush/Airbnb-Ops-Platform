import os
from dataclasses import replace
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "mini_city"
TEST_DB = os.getenv("AIRBNB_TEST_DB_NAME", "airbnb_test")


@pytest.fixture(scope="session")
def mini_city() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def test_db():
    """A Database pointing at a separate test database (never the main one).

    Skips when AIRBNB_DB_HOST is not set, so unit tests run without Postgres.
    """
    if not os.getenv("AIRBNB_DB_HOST"):
        pytest.skip("AIRBNB_DB_HOST not set")

    from sqlalchemy import create_engine, text

    from airbnb_ops.db import Database
    from airbnb_ops.settings import DbSettings

    base = DbSettings.from_env()
    assert TEST_DB != base.name, "test database must differ from the main database"

    admin = create_engine(replace(base, name="postgres").url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("select 1 from pg_database where datname = :n"), {"n": TEST_DB}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()
    return Database(replace(base, name=TEST_DB))


@pytest.fixture(scope="session")
def loaded_db(test_db, mini_city):
    """Test database with the mini fixture loaded into the core schema."""
    from airbnb_ops.ingest.load import load_city

    load_city(test_db, mini_city, salt="test-salt")
    return test_db
