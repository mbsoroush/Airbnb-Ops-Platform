"""Thin database wrapper (requires the `db` extra)."""
from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

from .settings import DbSettings


class Database:
    def __init__(self, settings: DbSettings | None = None) -> None:
        self.settings = settings or DbSettings.from_env()
        self.engine = create_engine(self.settings.url, pool_pre_ping=True)

    def execute_script(self, sql: str) -> None:
        """Run one or more statements in a single transaction."""
        with self.engine.begin() as conn:
            conn.exec_driver_sql(sql)

    def fetch(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Run a read-only query and return (column names, rows)."""
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute(sql)
                columns = [d[0] for d in cur.description]
                rows = cur.fetchall()
            raw.rollback()
            return columns, rows
        finally:
            raw.close()

    def fetch_row(self, sql: str) -> dict[str, Any]:
        """Run a read-only query and return its first row as {column: value}."""
        columns, rows = self.fetch(sql)
        if not rows:
            raise LookupError("query returned no rows")
        return dict(zip(columns, rows[0], strict=True))

    def scalar(self, sql: str):
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar()

    def ensure_reader_role(self, role: str, password: str, schema: str = "analytics") -> None:
        """Create (or update) a login role that can only read `schema`. Idempotent.

        Default privileges make tables and materialized views created later in `schema`
        readable too, so rebuilding the view does not silently revoke access. The role gets
        no access to `core` and cannot create objects anywhere.
        """
        from psycopg2 import sql

        ident = sql.Identifier
        statements = [
            sql.SQL("{} ROLE {} LOGIN PASSWORD {}"),  # filled in below (CREATE or ALTER)
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                ident(self.settings.name), ident(role)
            ),
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(ident(schema)),
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(ident(schema), ident(role)),
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                ident(schema), ident(role)
            ),
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(
                ident(schema), ident(role)
            ),
        ]
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                verb = "ALTER" if cur.fetchone() else "CREATE"
                statements[0] = statements[0].format(
                    sql.SQL(verb), ident(role), sql.Literal(password)
                )
                for statement in statements:
                    cur.execute(statement)
            raw.commit()
        finally:
            raw.close()

    def copy_frame(self, df: pd.DataFrame, table: str, columns: Sequence[str]) -> int:
        """Bulk-load a dataframe with COPY (far faster than INSERT for millions of rows)."""
        cols = list(columns)
        buf = io.StringIO()
        df[cols].to_csv(buf, index=False, header=False, na_rep="")
        buf.seek(0)
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.copy_expert(
                    f"COPY {table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv)", buf
                )
            raw.commit()
        finally:
            raw.close()
        return len(df)
