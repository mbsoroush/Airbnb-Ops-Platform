# EXPLAIN ANALYZE notes: baseline neighbourhood summary

Plan: `reports/baseline_explain_analyze.txt` (regenerate with `airbnb-ops perf-report`).

Observations come from one run on PostgreSQL 16 with the Munich snapshot (7,493 listings,
2,734,952 calendar rows, 247,636 reviews), total execution about 375 ms. Row counts and plan
shape depend on the data and should match your run; millisecond timings depend on the machine.

## 1. The calendar table is scanned twice, and the first scan only finds one date

`InitPlan 1` evaluates `SELECT MIN(date) + 30` with a parallel sequential scan over all of
`core.calendar_day` (911,651 rows x 3 workers = 2,734,953). That subplan takes about 202 ms,
roughly 54% of the 375 ms total, just to produce a single value. The main aggregation then
scans the whole table again.

## 2. The date filter discards about 92% of the rows it reads

The main scan applies `Filter: (date < $1)`, keeping about 218,100 rows (72,700 x 3) and
removing about 2,516,853 (`Rows Removed by Filter: 838951` per worker). The primary key is
`(listing_id, date)`, which leads with `listing_id`, so it cannot serve a predicate on `date`
alone, and the planner has no choice but a sequential scan.

## 3. Large input, tiny output, repeated on every run

The plan touches 42,531 buffer pages (`shared hit=19631 read=22900`, about 340 MB) and also
scans all 247,636 review rows, to produce 25 result rows (one per neighbourhood). It builds
7,493 per-listing aggregates, joins and sorts them, then throws almost everything away. If a
dashboard ran this on every open, every viewer would pay the full cost again, even though the
answer only changes when the data does.

## What this suggests

- Precompute: store the 25-row answer in a materialized view and refresh it when data changes
  (`sql/02_create_materialized_view.sql`). Dashboards then read 25 rows from an indexed object.
- Not yet measured (hypothesis only): an index such as
  `calendar_day (date) INCLUDE (listing_id, available)` should let `MIN(date)` and the 30-day
  window avoid full scans. It would help the baseline and the view refresh, at the cost of
  extra storage and slower loads. Worth a follow-up experiment.
