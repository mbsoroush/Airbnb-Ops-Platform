.PHONY: install lint test test-db db-up db-down ingest view features features-v2 perf bi-up bi-setup bi-down af-up af-trigger af-test af-down run

install:
	python -m pip install -e ".[db,dev,features]"

lint:
	python -m ruff check .

test:
	python -m pytest

# Includes integration tests. Uses a separate airbnb_test database, never your main data.
test-db:
	AIRBNB_DB_HOST=localhost python -m pytest

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

# Needs data/raw/munich/{listings,calendar,reviews}.csv.gz
ingest:
	docker compose run --rm ingest

# (Re)create the materialized view analytics.mv_airbnb_neighbourhood_summary
view:
	airbnb-ops build-view

# Feature dataset: versioned feature datasets under data/features/ (needs make ingest first).
# v1 uses the earliest valid cutoff, derived from the data. v2 is a comparison dataset whose
# cutoff avoids the Christmas and New Year label window of v1.
features:
	airbnb-ops build-features --version v1

features-v2:
	airbnb-ops build-features --version v2 --cutoff 2027-02-22 --cutoff-reason "Avoids the Christmas and New Year label window of v1; comparison dataset, not chosen by model score."

# EXPLAIN ANALYZE + benchmark; writes reports/sql_performance.md and the plan
perf:
	airbnb-ops perf-report

# Metabase: start it, then (once Metabase is up) create the read-only DB role and
# provision admin, connection and dashboard. Needs AIRBNB_READER_PASSWORD and
# METABASE_ADMIN_PASSWORD in .env (see .env.example) and the view built (make view).
bi-up:
	docker compose up -d metabase

bi-setup:
	airbnb-ops create-reader
	airbnb-ops metabase-setup

bi-down:
	docker compose stop metabase

# Airflow: start it (needs AIRFLOW_ADMIN_PASSWORD in .env and the view built), then trigger the DAG.
# Open http://localhost:8080. The run report lands in reports/airflow_runs/.
af-up:
	docker compose up -d airflow

af-trigger:
	docker compose exec airflow airflow dags unpause airbnb_neighbourhood_summary
	docker compose exec airflow airflow dags trigger airbnb_neighbourhood_summary

# Run the DAG once in-process (no scheduler), handy for debugging.
af-test:
	docker compose exec airflow airflow dags test airbnb_neighbourhood_summary

af-down:
	docker compose stop airflow

run:
	airbnb-ops run
