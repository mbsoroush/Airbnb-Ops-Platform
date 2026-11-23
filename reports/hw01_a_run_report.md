# HW01-A Run Report

- Run at (UTC): 2026-11-23T08:30:18+00:00
- Input listings: 8
- Output neighbourhoods: 5
- Neighbourhoods with unknown segment: 0
- PII handling: host_name dropped, host_id replaced by host_key then dropped from output
- Validation: passed
- Output file: `data/processed/airbnb_neighbourhood_summary.csv`

## Summary preview

| neighbourhood | num_listings | avg_price | median_price | avg_minimum_nights | availability_365_avg | total_reviews | reviews_per_listing | tourism_segment | priority_level |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Centrum-West | 2 | 195.0 | 195.0 | 2.5 | 100.0 | 43 | 21.5 | tourist-heavy | high |
| De Baarsjes | 2 | 135.0 | 135.0 | 3.5 | 130.0 | 48 | 24.0 | local-heavy | low |
| De Pijp | 1 | 135.0 | 135.0 | 2.0 | 210.0 | 44 | 44.0 | mixed | medium |
| Oud-Noord | 2 | 100.0 | 100.0 | 1.5 | 280.0 | 27 | 13.5 | emerging | medium |
| Westerpark | 1 | 155.0 | 155.0 | 2.0 | 140.0 | 36 | 36.0 | mixed | medium |
