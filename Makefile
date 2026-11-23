.PHONY: install lint test test-db db-up db-down ingest view perf run

install:
	python -m pip install -e ".[db,dev]"

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

# EXPLAIN ANALYZE + benchmark; writes reports/sql_performance.md and the plan
perf:
	airbnb-ops perf-report

run:
	airbnb-ops run
