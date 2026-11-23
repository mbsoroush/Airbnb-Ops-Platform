-- Materialized view for dashboards: one row per neighbourhood, computed once and stored.
-- Both availability windows (30 day and full year) come from one grouped aggregation (FILTER).
-- Building is slow-ish but happens rarely; reading the result is what dashboards do.
-- Rebuild with this script; refresh later with REFRESH MATERIALIZED VIEW CONCURRENTLY.
CREATE SCHEMA IF NOT EXISTS analytics;

DROP MATERIALIZED VIEW IF EXISTS analytics.mv_airbnb_neighbourhood_summary;

CREATE MATERIALIZED VIEW analytics.mv_airbnb_neighbourhood_summary AS
WITH bounds AS (
    SELECT MIN(date) AS start_date FROM core.calendar_day
),
calendar_rates AS (
    SELECT
        c.listing_id,
        AVG(CASE WHEN c.available THEN 1.0 ELSE 0.0 END)
            FILTER (WHERE c.date < b.start_date + 30) AS availability_30_rate,
        AVG(CASE WHEN c.available THEN 1.0 ELSE 0.0 END) AS availability_365_rate
    FROM core.calendar_day AS c
    CROSS JOIN bounds AS b
    GROUP BY c.listing_id
),
review_counts AS (
    SELECT
        listing_id,
        COUNT(*) AS total_reviews
    FROM core.review
    GROUP BY listing_id
)
SELECT
    l.neighbourhood,
    COUNT(*) AS num_listings,
    ROUND(AVG(l.price), 2) AS avg_price,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.price))::numeric, 2) AS median_price,
    ROUND(AVG(l.minimum_nights), 2) AS avg_minimum_nights,
    COALESCE(SUM(r.total_reviews), 0) AS total_reviews,
    ROUND(COALESCE(SUM(r.total_reviews), 0)::numeric / COUNT(*), 2) AS reviews_per_listing,
    ROUND(AVG(cr.availability_30_rate)::numeric, 4) AS availability_30_rate,
    ROUND(AVG(cr.availability_365_rate)::numeric, 4) AS availability_365_rate,
    NOW() AS refreshed_at
FROM core.listing AS l
LEFT JOIN calendar_rates AS cr ON cr.listing_id = l.listing_id
LEFT JOIN review_counts AS r ON r.listing_id = l.listing_id
GROUP BY l.neighbourhood;

-- A unique index is required for REFRESH ... CONCURRENTLY (refresh without blocking readers).
CREATE UNIQUE INDEX ux_mv_neighbourhood_summary_neighbourhood
    ON analytics.mv_airbnb_neighbourhood_summary (neighbourhood);

-- Supports the "top neighbourhoods" dashboard card ordering.
CREATE INDEX ix_mv_neighbourhood_summary_num_listings
    ON analytics.mv_airbnb_neighbourhood_summary (num_listings DESC);
