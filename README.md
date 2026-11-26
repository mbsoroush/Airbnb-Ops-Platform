# Airbnb MLOps Platform

[![ci](https://github.com/mbsoroush/Airbnb-MLOps-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mbsoroush/Airbnb-MLOps-Platform/actions/workflows/ci.yml)

A small, production-minded data platform built around public Airbnb data: reproducible
ingestion, PII handling, validated analytics, SQL performance tuning, a dashboard defined as
code, and scheduled orchestration with Airflow.

## Status

| Milestone | Scope | State |
|---|---|---|
| 1. Package and ingestion | CLI, PII handling, cleaning, Postgres loader, tests, CI, Docker | done |
| 2. SQL performance | baseline query, `EXPLAIN ANALYZE`, materialized view, indexes, benchmark | done |
| 2b. Dashboard | Metabase on the materialized view, provisioned from code | done |
| 3. Orchestration | Airflow DAG: refresh, validate, branch, report | done |
| 4. Feature dataset | extended ingest, versioned feature datasets v1/v2, validation, PII audit | done |

## Architecture

```mermaid
flowchart LR
    A[Inside Airbnb files<br/>listings, calendar, reviews] --> B[clean + PII pseudonymization]
    B --> C[(Postgres: core schema)]
    C --> D[(analytics.mv_airbnb_neighbourhood_summary)]
    D --> E[Metabase dashboard<br/>read-only role]
    F[Airflow DAG, daily] -->|refresh concurrently| D
    F -->|validate| D
    F --> G[run report<br/>success or failure]
    C --> I[data/features<br/>versioned feature dataset, DVC<br/>validation + PII audit]
    H[CI: lint, tests, DAG run] -.-> B
```

## Quickstart

```bash
make install            # editable install with db + dev extras
make test               # unit tests (database tests are skipped)

make db-up              # Postgres 16 via docker compose
# place Munich files in data/raw/munich/ (see the README there), then:
make ingest

make features           # data/features/listing_availability_features_v1.* plus metadata, validation, PII audit
make features-v2        # comparison dataset with a later cutoff

make test-db            # full tests incl. database ones (separate airbnb_test database)
make perf               # EXPLAIN ANALYZE + benchmark -> reports/sql_performance.md

make view               # (re)build the materialized view the dashboard reads
cp .env.example .env    # then set AIRBNB_READER_PASSWORD and METABASE_ADMIN_PASSWORD
make bi-up              # Metabase on http://localhost:3000 (first start takes a minute or two)
make bi-setup           # read-only DB role + Metabase admin, connection and dashboard
```

Tiny demo pipeline on the bundled CSVs (no database needed):

```bash
airbnb-ops run          # writes data/processed/... and reports/hw01_a_run_report.md
```

## SQL performance

`make perf` measures three ways of producing the neighbourhood summary on the Munich snapshot
and writes `reports/sql_performance.md`, `reports/baseline_explain_analyze.txt` (the plan) and
compares them. `reports/explain_notes.md` explains what the plan shows.

- **Naive join** of listings, calendar and reviews: slow, and also wrong. Joining tables of
  different grain repeats rows, so `AVG(price)` is weighted by review counts.
- **Baseline**: CTEs aggregate to listing grain first. Correct, but it re-reads millions of
  calendar rows to produce 25 result rows.
- **Materialized view** `analytics.mv_airbnb_neighbourhood_summary` with a unique index (for
  `REFRESH ... CONCURRENTLY`) and a `num_listings` index. Dashboards only read this.

A test asserts the view returns exactly the same numbers as the baseline.

## Dashboard (Metabase)

![Metabase dashboard](screenshots/metabase_dashboard.png)

The dashboard is defined as data in `src/airbnb_ops/metabase/dashboard.py` and provisioned
through Metabase's REST API by `airbnb-ops metabase-setup` (run by `make bi-setup`):

- **Cards:** listings, average/median price, review activity and availability by
  neighbourhood, a top-10 table, and a data-freshness tile. Every card is a SQL query on
  `analytics.mv_airbnb_neighbourhood_summary`, so opening the dashboard never runs a big join.
- **Idempotent:** objects are found by name and updated in place. Edit the file, run
  `make bi-setup` again, and Metabase converges to what is in code.
- **Least privilege:** Metabase connects as `metabase_reader`, a role that can read only the
  `analytics` schema (`airbnb-ops create-reader`). Default privileges keep that access when
  the view is rebuilt. It cannot read `core` or create anything.
- **Secrets** come from `.env` (gitignored): `METABASE_ADMIN_PASSWORD`,
  `AIRBNB_READER_PASSWORD`. Nothing secret is committed.
- `airbnb-ops metabase-setup --dry-run` prints the full dashboard definition without calling
  Metabase. The image is pinned in `docker-compose.yml` (override with `METABASE_VERSION`).

**Data-quality note:** some listings have extreme prices (two private rooms above 68,000 per
night), so neighbourhood averages can be badly skewed. The price card shows the median next to
the average for that reason. About a third of Munich listings have no price at all.

**Manual fallback:** Metabase's API changes between versions. If automated setup ever fails,
add the database in the Metabase UI with the reader credentials and create each question as
a native query using the SQL from `--dry-run`.

The Metabase app database is a local H2 file in a Docker volume, which is fine for development;
production should use Postgres for it.

## Orchestration (Airflow)

DAG `airbnb_neighbourhood_summary` (`dags/`) runs daily at 03:00 UTC:

```
read_config -> refresh_summary -> validate_summary -> choose_report_path -> write_success_report
                                                                         \-> write_failure_report
```

- **Thin DAG, tested logic.** All behaviour lives in `src/airbnb_ops/pipeline.py`, which needs
  only a tiny `SqlRunner` protocol. Airflow supplies a `PostgresHook` adapter; tests use a fake
  runner or a real Postgres. The module imports neither pandas nor SQLAlchemy.
- **Refresh** uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` (readers are never blocked), creates
  the view if missing, and rebuilds it with the `rebuild` run parameter after the SQL changes.
- **Validation** (`sql/03_validate_summary.sql`): *error* checks fail the run (empty view, null
  neighbourhoods, negative prices, availability outside 0..1, view not reconciling with `core`);
  *warn* checks are reported only (price outliers above a threshold, share of listings with no
  price).
- **Branching:** a markdown report is written to `reports/airflow_runs/` either way. On failure
  the report is written first and then the task raises, so the run is red in the UI *and*
  leaves evidence.
- **Config, no secrets in code:** Connection `airbnb_warehouse` (env `AIRFLOW_CONN_*`) and
  Variables `airbnb_reports_dir`, `airbnb_price_outlier_threshold`, `airbnb_max_null_price_share`.
- **Settings:** `catchup=False`, `max_active_runs=1`, retries on data tasks, none on the report.

```bash
make db-up && make ingest && make view     # data and view must exist
# set AIRFLOW_ADMIN_PASSWORD in .env, then:
make af-up                                  # http://localhost:8080, user: admin
make af-trigger                             # unpause + trigger; see reports/airflow_runs/
```

**Dev-only caveat:** the container runs `airflow standalone` (SQLite metadata DB, one process,
SimpleAuthManager with a plaintext password file). Production would use the official multi-service
deployment, a Postgres metadata DB, and a real auth manager. The Airflow version is pinned
(`AIRFLOW_VERSION`, default 3.4.0); CI installs it with the official constraints file and runs the
DAG end to end on the small fixture city.

## Feature dataset

`airbnb-ops build-features` turns the `core` tables into one clean, versioned table: one row per
listing at one cutoff date, 26 model-input columns and a binary label. It is the input for the
experiment tracking and serving parts.

```
core tables --SQL aggregation--> pure assembly --> validation --> data/features/ + reports/
```

- **Aggregated in SQL, never in pandas.** Reviews and calendar rows are summed up by numbered
  SQL files (`sql/11` to `sql/14`); only one row per listing reaches Python. Dates are bound
  parameters, not formatted into the SQL.
- **Windows.** Features use the 90 days up to and including the cutoff (and the last 30 of
  them); the label uses the 30 days strictly after it. Reviews are filtered with
  `review_date <= cutoff`.
- **Label.** `high_demand_proxy = 1` when `future_available_rate_30d <= 0.30`. A day is
  unavailable when it is booked **or blocked by the host**, so this is a low-availability
  proxy, not confirmed booking demand.
- **Output files** in `data/features/` (version `v1` shown): `listing_availability_features_v1.csv`
  and `.parquet`, `_metadata.json` (cutoff and how it was chosen, windows, the column contract,
  forbidden fields, row counts, file hashes, limitations), `_validation_report.json` and
  `pii_audit_v1.csv`. A readable summary goes to `reports/features_v1.md`.
- **A version is immutable.** Rebuilding gives identical bytes; if the content would differ the
  command refuses unless you pass `--overwrite` (or choose a new `--version`).

**Cutoffs.** `v1` uses the earliest valid cutoff (calendar start + 90 days), derived from the
data, not typed in. `v2` uses a configured cutoff, 2027-02-22, chosen only because its label
window avoids Christmas and New Year; it was never chosen by model score. `v1` and `v2` contain
the same listings, so they are not independent evidence for each other.

**Missing values** (each rule is counted in the metadata and the report): `bathrooms` is parsed
from `bathrooms_text`; missing room/property type becomes `unknown`; a missing
`instant_bookable` or `host_is_superhost` becomes `False` (a modeling choice, not a fact); rows
without `accommodates`, `minimum_nights` or `maximum_nights` are dropped; listings without a
full history or label window are dropped. Price, bedrooms, beds and bathrooms stay missing for
the model pipeline to impute.

**Privacy.** `host_key` and `reviewer_key` are only used inside SQL to count a host's listings
and distinct reviewers; they are never returned. Review comments are read at ingest only to
store their length (`comment_len`); the text is discarded and never reaches the warehouse. The
PII audit table lists what happens to every sensitive column, and validation fails if a
forbidden column appears in the feature table.

**Limitations (read before trusting a score).**
- Inside Airbnb's calendar is a forward-looking snapshot. The history window and the label
  window both describe the future as seen on one day, so this is **not a true temporal split**;
  that would need several snapshots.
- Reviews end on the snapshot date, before any valid cutoff, so the review features are the
  same for every cutoff, and `days_since_last_review` differs between cutoffs only by a constant.
- Because `available_rate_last_30d` and the label come from the same calendar, a model can score
  well on this data without proving that it would predict real bookings.

**Source inspection.** Every build starts with a connection check and inspects the source
tables (`sql/15`, `sql/16`): row counts, null counts, the tables and columns of `core`, and
whether calendar prices exist. The result is stored in the metadata and shown in the report.
The Munich calendar has no `price` or `adjusted_price` column, so no calendar price features are
built; `listing_price` comes from `core.listing`.

**Unusable columns.** Columns that are constant or more than 95% missing are dropped when they
are not part of the column contract. Contract columns are never dropped, because the serving
API fixes them; a constant or almost empty contract column is kept and triggers a warning in
the build output and the validation report. Today the table has only contract columns, so the
rule is a safety net: it matters when a new feature is added.

**Ingest changes.** `sql/04_core_ml_columns.sql` adds the extra columns (bedrooms, beds,
bathrooms text, maximum nights, instant bookable, superhost, comment length) with
`ADD COLUMN IF NOT EXISTS`, so existing databases are upgraded in place. The new columns are
optional in the input files: a file without them (such as the small test fixtures) still loads,
with NULL. After re-ingesting Munich, run `make view` to refresh the dashboard view.

**DVC.** `dvc.yaml` has `build_features_v1` and `build_features_v2` stages. DVC cannot track
Postgres state, so the stages depend on the raw files and the code and assume the database was
loaded from those files by `make ingest`.

**Tests.** The builder is tested without a database by a fake reader backed by an independent
pandas implementation (`tests/features_reference.py`). With Postgres (`make test-db`) the real
SQL is compared against that reference on the `mini_city_ml` fixture, which has a 140 day
calendar and one listing for every rule above (see `tests/fixtures/make_mini_city_ml.py`).

## Design decisions

- **PII never enters the warehouse.** Only needed columns are read (names and free text such
  as `comments` are never loaded). `host_id` and `reviewer_id` become salted SHA-256 keys.
- **Bulk loading uses `COPY`**, in chunks for the calendar table. A full Munich snapshot
  (about 2.7M calendar rows) loads in roughly 30 seconds.
- **Cleaning is pure functions**, so it is unit-tested without a database. Real quirks handled:
  prices stored as text (`"$1,250.00"`), about a third of prices missing, duplicate review ids.
- **Config comes from the environment**; no secrets in the repo. See `.env.example`.
- **`core` has primary keys only.** Performance work is a separate, measured step, and derived
  objects live in the `analytics` schema, never in `core`.
- **SQL lives in the package** (`src/airbnb_ops/sql/`) as the single source of truth for the
  CLI, tests and the Airflow DAG. A test rejects `SELECT *`.
- **Integration tests use their own database** (`airbnb_test`), so they cannot touch loaded data.
- **The Metabase client is standard-library only** with an injectable HTTP transport, so the
  provisioning flow is tested against an in-memory fake of the API, with no server needed.
- **Optional `.env` loading** never overrides real environment variables.

## Data and attribution

Data: [Inside Airbnb](https://insideairbnb.com/get-the-data/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Munich snapshot dated 23 September
2026. Test fixtures are a small anonymized slice of the Albany snapshot (16 September 2026).
Raw city files are not committed.

## Layout

```
src/airbnb_ops/   package (cli, pii, transform, validate, analytics, ingest/, features/, metabase/)
src/airbnb_ops/sql/  core schema, baseline query, materialized view
tests/            unit tests + fixtures (database tests need Postgres)
reports/          generated performance reports and plan notes
dags/             Airflow DAG (thin wrapper around airbnb_ops/pipeline.py)
notebooks/        thin walkthroughs that import from the package
```
