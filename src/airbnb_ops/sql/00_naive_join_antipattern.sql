-- ANTI-PATTERN, kept only for comparison in the performance report.
-- Joining listing (1 row per listing) to calendar (30 rows per listing in the window) and
-- review (N rows per listing) multiplies rows: every listing is repeated 30 x N times.
-- AVG() then weights each listing by its review count, so the numbers are wrong as well as slow.
SELECT
    l.neighbourhood,
    COUNT(DISTINCT l.listing_id) AS num_listings,
    ROUND(AVG(l.price), 2) AS avg_price,
    COUNT(DISTINCT r.review_id) AS total_reviews,
    ROUND(AVG(CASE WHEN c.available THEN 1.0 ELSE 0.0 END), 4) AS availability_30_rate
FROM core.listing AS l
JOIN core.calendar_day AS c
    ON c.listing_id = l.listing_id
   AND c.date < (SELECT MIN(date) + 30 FROM core.calendar_day)
LEFT JOIN core.review AS r
    ON r.listing_id = l.listing_id
GROUP BY l.neighbourhood
ORDER BY num_listings DESC;
