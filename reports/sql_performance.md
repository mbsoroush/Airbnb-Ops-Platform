# SQL performance report

Generated: 2026-11-23T13:03:19+00:00
Database: PostgreSQL 16.16 (Debian 16.16-1.pgdg13+1)
Rows: `listing` 7,493, `calendar_day` 2,734,952, `review` 247,636; view `analytics.mv_airbnb_neighbourhood_summary` 25
Each query ran 3 times; timings include fetching all result rows.

## Latency

| Query | Best (s) | Average (s) | Speedup vs baseline (best) |
| --- | ---: | ---: | ---: |
| Naive three-table join | 2.4946 | 2.5356 | 0.0x |
| Baseline (pre-aggregated CTEs) | 0.0786 | 0.0790 | 1.0x |
| Materialized view read | 0.0009 | 0.0009 | 87.1x |

## Correctness: the naive join gives wrong averages

Joining listings to calendar days and reviews repeats each listing once per
(calendar day x review), so `AVG(price)` weights listings by their review count.

| Neighbourhood | Naive avg price | Correct avg price | Error |
| --- | ---: | ---: | ---: |
| Ludwigsvorstadt-Isarvorstadt | 310.75 | 370.48 | -16.1% |
| Maxvorstadt | 333.06 | 744.57 | -55.3% |
| Neuhausen-Nymphenburg | 277.90 | 260.83 | +6.5% |
| Au-Haidhausen | 211.03 | 264.97 | -20.4% |
| Schwabing-West | 223.85 | 267.97 | -16.5% |

## What changed

- Baseline: aggregate calendar and reviews to listing grain in CTEs before joining.
- `analytics.mv_airbnb_neighbourhood_summary`: the summary is computed once and stored; dashboards only read it.
- Both availability windows (30 day and full year) come from one grouped aggregation.
- A unique index on `neighbourhood` enables `REFRESH ... CONCURRENTLY`;
  an index on `num_listings` supports the top-neighbourhoods card.
- The trade-off: the view is as fresh as its last refresh, so the pipeline (Airflow,
  milestone 3) refreshes and validates it on a schedule.

See `reports/baseline_explain_analyze.txt` and `reports/explain_notes.md` for the plan.
