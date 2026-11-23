"""Thin database wrapper (requires the `db` extra)."""
from __future__ import annotations

import io
from collections.abc import Sequence

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

    def scalar(self, sql: str):
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar()

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
