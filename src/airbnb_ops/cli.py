"""Command line interface: `airbnb-ops run`."""
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from .config import PipelineConfig
from .extract import read_csv_checked
from .pii import handle_pii
from .settings import load_dotenv, pii_salt, reader_password, reader_user
from .transform import build_neighbourhood_summary
from .validate import validate_summary

app = typer.Typer(help="Airbnb ops pipeline.", no_args_is_help=True)
console = Console()


def _markdown_table(df) -> str:
    """Render a dataframe as a markdown table without extra dependencies."""
    header = "| " + " | ".join(df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


@app.callback()
def main() -> None:
    """Airbnb ops pipeline."""
    load_dotenv()  # optional .env in the working directory; real env vars take precedence


@app.command()
def run() -> None:
    """Read inputs, handle PII, transform, validate, write CSV and report."""
    cfg = PipelineConfig()

    listings = read_csv_checked(cfg.listings_path)
    segments = read_csv_checked(cfg.segments_path)
    n_in = len(listings)

    listings = handle_pii(listings)
    summary = build_neighbourhood_summary(listings, segments)
    validate_summary(summary)

    cfg.output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.report_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(cfg.output_path, index=False)

    unknown = int((summary["tourism_segment"] == "unknown").sum())
    report = f"""# HW01-A Run Report

- Run at (UTC): {datetime.now(timezone.utc).isoformat(timespec="seconds")}
- Input listings: {n_in}
- Output neighbourhoods: {len(summary)}
- Neighbourhoods with unknown segment: {unknown}
- PII handling: host_name dropped, host_id replaced by host_key then dropped from output
- Validation: passed
- Output file: `{cfg.output_path}`

## Summary preview

{_markdown_table(summary)}
"""
    cfg.report_path.write_text(report, encoding="utf-8")
    console.print(f"[green]Done.[/green] Wrote {cfg.output_path} and {cfg.report_path}")


@app.command()
def ingest(
    raw_dir: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Folder with listings, calendar, reviews files."
    ),
    append: bool = typer.Option(False, "--append", help="Do not truncate tables first."),
    chunksize: int = typer.Option(500_000, help="Calendar rows per chunk."),
) -> None:
    """Clean an Inside Airbnb city snapshot and load it into Postgres (core schema)."""
    try:
        from .db import Database
        from .ingest.load import load_city
    except ImportError as exc:  # sqlalchemy / psycopg2 missing
        console.print("[red]Database extras missing.[/red] Install with: pip install '.[db]'")
        raise typer.Exit(code=1) from exc

    counts = load_city(
        Database(), raw_dir, salt=pii_salt(), truncate=not append, chunksize=chunksize
    )
    for table, n in counts.items():
        console.print(f"core.{table}: {n:,} rows")


def _db_or_exit():
    try:
        from .db import Database
    except ImportError as exc:
        console.print("[red]Database extras missing.[/red] Install with: pip install '.[db]'")
        raise typer.Exit(code=1) from exc
    return Database()


@app.command("build-view")
def build_view() -> None:
    """Create (or recreate) the materialized view analytics.mv_airbnb_neighbourhood_summary."""
    from .analytics import VIEW, build_summary_view

    db = _db_or_exit()
    build_summary_view(db)
    console.print(f"[green]Built[/green] {VIEW}: {db.scalar(f'select count(*) from {VIEW}')} rows")


@app.command("perf-report")
def perf_report_cmd(
    repeats: int = typer.Option(3, min=1, help="Runs per query (best and average reported)."),
    reports_dir: Path = typer.Option(Path("reports"), help="Where to write the report files."),
) -> None:
    """EXPLAIN ANALYZE the baseline, build the view, benchmark, and write the reports."""
    from .analytics import perf_report

    timings = perf_report(_db_or_exit(), reports_dir, repeats)
    base = timings["baseline"].best
    for t in timings.values():
        console.print(f"{t.label:<34} best {t.best:8.4f}s   {base / t.best:>8,.1f}x vs baseline")
    console.print(f"Wrote reports to {reports_dir}/")


@app.command("create-reader")
def create_reader() -> None:
    """Create or update the read-only Postgres role Metabase connects with."""
    from .constants import SCHEMA

    password = reader_password()
    if not password:
        console.print(
            "[red]AIRBNB_READER_PASSWORD is not set.[/red] Put it in .env "
            "(for example: openssl rand -hex 16)."
        )
        raise typer.Exit(code=1)
    _db_or_exit().ensure_reader_role(reader_user(), password, SCHEMA)
    console.print(f"[green]Role[/green] {reader_user()} can read the {SCHEMA} schema only")


@app.command("metabase-setup")
def metabase_setup(
    url: str = typer.Option(
        "http://localhost:3000", envvar="METABASE_URL", help="Metabase URL from this machine."
    ),
    admin_email: str = typer.Option(
        "admin@example.com", envvar="METABASE_ADMIN_EMAIL", help="First admin's email."
    ),
    db_host: str = typer.Option(
        "postgres", envvar="METABASE_DB_HOST", help="Postgres host as seen from Metabase."
    ),
    db_port: int = typer.Option(5432, envvar="METABASE_DB_PORT"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the dashboard; call nothing."),
) -> None:
    """Provision Metabase: admin, warehouse connection, collection, cards and dashboard."""
    import os

    from .metabase.client import MetabaseClient, MetabaseError
    from .metabase.dashboard import default_dashboard
    from .metabase.provision import WarehouseConnection, provision
    from .settings import DbSettings

    spec = default_dashboard()
    if dry_run:
        typer.echo(f"Collection: {spec.collection}\nDashboard:  {spec.name}\n")
        for card in spec.cards:
            typer.echo(
                f"- {card.name} [{card.display}] at row {card.row}, col {card.col}, "
                f"{card.width}x{card.height}\n{card.sql}\n"
            )
        return

    admin_password = os.getenv("METABASE_ADMIN_PASSWORD")
    db_password = reader_password()
    if not admin_password or not db_password:
        console.print(
            "[red]Set METABASE_ADMIN_PASSWORD and AIRBNB_READER_PASSWORD[/red] (for example in "
            ".env; use long random values, e.g. openssl rand -hex 16)."
        )
        raise typer.Exit(code=1)

    warehouse = WarehouseConnection(
        name="Airbnb Warehouse",
        host=db_host,
        port=db_port,
        dbname=DbSettings.from_env().name,
        user=reader_user(),
        password=db_password,
    )
    try:
        result = provision(MetabaseClient(url), admin_email, admin_password, warehouse, spec)
    except (MetabaseError, TimeoutError) as exc:
        console.print(f"[red]Metabase setup failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    state = "first-time setup" if result.first_run else "updated existing setup"
    console.print(
        f"[green]Done[/green] ({state}): {result.cards_created} cards created, "
        f"{result.cards_updated} updated.\nDashboard: {result.dashboard_url}"
    )


if __name__ == "__main__":
    app()
