-- One row per listing with calendar rows in the 30 day label window (cutoff, label_end].
-- Only dates strictly after the cutoff are used. The binary label is derived in Python.
SELECT
    listing_id,
    COUNT(*) AS future_calendar_days_observed_30d,
    SUM(CASE WHEN available THEN 1 ELSE 0 END) AS future_available_days_30d,
    CAST(AVG(CASE WHEN available THEN 1.0 ELSE 0.0 END) AS double precision)
        AS future_available_rate_30d
FROM core.calendar_day
WHERE date > CAST(:cutoff_date AS date)
  AND date <= CAST(:label_end_date AS date)
GROUP BY listing_id;
