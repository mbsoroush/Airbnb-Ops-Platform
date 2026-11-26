-- One row per listing with calendar rows in the 90 day history window.
-- Parameters: history_start_date, recent_start_date (first day of the 30 day window), cutoff_date.
-- The calendar_days_observed_* columns are used to drop listings with incomplete windows.
SELECT
    listing_id,
    COUNT(*) AS calendar_days_observed_90d,
    SUM(CASE WHEN available THEN 1 ELSE 0 END) AS available_days_last_90d,
    CAST(AVG(CASE WHEN available THEN 1.0 ELSE 0.0 END) AS double precision)
        AS available_rate_last_90d,
    CAST(AVG(minimum_nights) AS double precision) AS avg_minimum_nights_calendar_last_90d,
    CAST(AVG(maximum_nights) AS double precision) AS avg_maximum_nights_calendar_last_90d,
    COUNT(*) FILTER (WHERE date >= CAST(:recent_start_date AS date))
        AS calendar_days_observed_30d,
    COUNT(*) FILTER (WHERE date >= CAST(:recent_start_date AS date) AND available)
        AS available_days_last_30d,
    CAST(AVG(CASE WHEN available THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE date >= CAST(:recent_start_date AS date)) AS double precision)
        AS available_rate_last_30d,
    CAST(AVG(minimum_nights) FILTER (WHERE date >= CAST(:recent_start_date AS date))
        AS double precision) AS avg_minimum_nights_calendar_last_30d,
    CAST(AVG(maximum_nights) FILTER (WHERE date >= CAST(:recent_start_date AS date))
        AS double precision) AS avg_maximum_nights_calendar_last_30d
FROM core.calendar_day
WHERE date >= CAST(:history_start_date AS date)
  AND date <= CAST(:cutoff_date AS date)
GROUP BY listing_id;
