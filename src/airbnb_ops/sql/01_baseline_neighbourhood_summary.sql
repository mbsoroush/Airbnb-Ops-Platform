-- Baseline: correct neighbourhood summary computed directly from core tables.
-- Each CTE aggregates to listing grain BEFORE joining, so no row multiplication.
-- Dashboards should NOT run this on every open; see 02_create_materialized_view.sql.
WITH calendar_30 AS (
    SELECT
        listing_id,
        AVG(CASE WHEN available THEN 1.0 ELSE 0.0 END) AS availability_30_rate
    FROM core.calendar_day
    WHERE date < (SELECT MIN(date) + 30 FROM core.calendar_day)
    GROUP BY listing_id
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
    ROUND(AVG(c.availability_30_rate)::numeric, 4) AS availability_30_rate
FROM core.listing AS l
LEFT JOIN calendar_30 AS c ON c.listing_id = l.listing_id
LEFT JOIN review_counts AS r ON r.listing_id = l.listing_id
GROUP BY l.neighbourhood
ORDER BY num_listings DESC;
