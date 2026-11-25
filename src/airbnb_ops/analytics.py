"""Neighbourhood analytics: baseline vs materialized view, timing and reporting.

Requires the `db` extra. SQL lives in src/airbnb_ops/sql/ and is the single source of truth
for the CLI, the tests and (later) the Airflow DAG.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .constants import VIEW
from .db import Database
from .sqlfiles import load_sql

SUMMARY_COLUMNS = [
    "neighbourhood", "num_listings", "avg_price", "median_price", "avg_minimum_nights",
    "total_reviews", "reviews_per_listing", "availability_30_rate",
]


def naive_sql() -> str:
    return load_sql("00_naive_join_antipattern.sql")


def baseline_sql() -> str:
    return load_sql("01_baseline_neighbourhood_summary.sql")


def view_sql() -> str:
    return load_sql("02_create_materialized_view.sql")


def dashboard_sql() -> str:
    """What a dashboard card runs: a read from the prepared view, never a fresh join."""
    return (
        "SELECT neighbourhood, num_listings, avg_price, median_price, total_reviews, "
        "reviews_per_listing, availability_30_rate, availability_365_rate "
        f"FROM {VIEW} ORDER BY num_listings DESC"
    )


def build_summary_view(db: Database) -> None:
    """(Re)create the materialized view and its indexes from scratch."""
    db.execute_script(view_sql())


def refresh_summary_view(db: Database, concurrently: bool = True) -> None:
    """Refresh data in place. CONCURRENTLY keeps the view readable during the refresh."""
    mode = "CONCURRENTLY " if concurrently else ""
    db.execute_script(f"REFRESH MATERIALIZED VIEW {mode}{VIEW}")


def explain_analyze(db: Database, sql: str) -> str:
    _, rows = db.fetch("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql)
    return "\n".join(r[0] for r in rows)


@dataclass
class QueryTiming:
    key: str
    label: str
    seconds: list[float] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)

    @property
    def best(self) -> float:
        return min(self.seconds)

    @property
    def avg(self) -> float:
        return sum(self.seconds) / len(self.seconds)


def time_query(db: Database, key: str, label: str, sql: str, repeats: int) -> QueryTiming:
    result = QueryTiming(key=key, label=label)
    for _ in range(repeats):
        start = time.perf_counter()
        result.columns, result.rows = db.fetch(sql)
        result.seconds.append(time.perf_counter() - start)
    return result


def run_benchmark(db: Database, repeats: int = 3) -> dict[str, QueryTiming]:
    return {
        "naive": time_query(db, "naive", "Naive three-table join", naive_sql(), repeats),
        "baseline": time_query(db, "baseline", "Baseline (pre-aggregated CTEs)", baseline_sql(),
                               repeats),
        "view": time_query(db, "view", "Materialized view read", dashboard_sql(), repeats),
    }


def _as_map(timing: QueryTiming, column: str) -> dict[str, float]:
    idx = timing.columns.index(column)
    return {row[0]: float(row[idx]) for row in timing.rows if row[idx] is not None}


def render_report(db_version: str, table_counts: dict[str, int], view_rows: int,
                  timings: dict[str, QueryTiming], repeats: int) -> str:
    base = timings["baseline"].best
    lines = [
        "# SQL performance report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Database: {db_version}",
        "Rows: " + ", ".join(f"`{t}` {n:,}" for t, n in table_counts.items())
        + f"; view `{VIEW}` {view_rows:,}",
        f"Each query ran {repeats} times; timings include fetching all result rows.",
        "",
        "## Latency",
        "",
        "| Query | Best (s) | Average (s) | Speedup vs baseline (best) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for t in timings.values():
        lines.append(
            f"| {t.label} | {t.best:.4f} | {t.avg:.4f} | {base / t.best:,.1f}x |"
        )

    naive_price = _as_map(timings["naive"], "avg_price")
    right_price = _as_map(timings["baseline"], "avg_price")
    top = [row[0] for row in timings["baseline"].rows[:5]]
    lines += [
        "",
        "## Correctness: the naive join gives wrong averages",
        "",
        "Joining listings to calendar days and reviews repeats each listing once per",
        "(calendar day x review), so `AVG(price)` weights listings by their review count.",
        "",
        "| Neighbourhood | Naive avg price | Correct avg price | Error |",
        "| --- | ---: | ---: | ---: |",
    ]
    for hood in top:
        if hood in naive_price and hood in right_price:
            n, r = naive_price[hood], right_price[hood]
            lines.append(f"| {hood} | {n:.2f} | {r:.2f} | {(n - r) / r * 100:+.1f}% |")

    lines += [
        "",
        "## What changed",
        "",
        "- Baseline: aggregate calendar and reviews to listing grain in CTEs before joining.",
        f"- `{VIEW}`: the summary is computed once and stored; dashboards only read it.",
        "- Both availability windows (30 day and full year) come from one grouped aggregation.",
        "- A unique index on `neighbourhood` enables `REFRESH ... CONCURRENTLY`;",
        "  an index on `num_listings` supports the top-neighbourhoods card.",
        "- The trade-off: the view is as fresh as its last refresh, so the pipeline (Airflow,",
        "  milestone 3) refreshes and validates it on a schedule.",
        "",
        "See `reports/baseline_explain_analyze.txt` and `reports/explain_notes.md` for the plan.",
        "",
    ]
    return "\n".join(lines)


def perf_report(db: Database, reports_dir: Path, repeats: int = 3) -> dict[str, QueryTiming]:
    """Capture the baseline plan, build the view, benchmark, and write both report files."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    plan = explain_analyze(db, baseline_sql())
    (reports_dir / "baseline_explain_analyze.txt").write_text(plan + "\n", encoding="utf-8")

    build_summary_view(db)
    timings = run_benchmark(db, repeats)

    counts = {
        t: db.scalar(f"select count(*) from core.{t}")
        for t in ("listing", "calendar_day", "review")
    }
    view_rows = db.scalar(f"select count(*) from {VIEW}")
    version = db.scalar("select version()").split(" on ")[0]
    report = render_report(version, counts, view_rows, timings, repeats)
    (reports_dir / "sql_performance.md").write_text(report, encoding="utf-8")
    return timings
