-- Data-quality metrics for the dashboard view, returned as ONE row of counts.
-- airbnb_ops.pipeline.validate_summary turns these into pass/fail checks.
-- {price_outlier_threshold} is filled in from Python as a float, never from user text.
SELECT
    (SELECT COUNT(*)
       FROM analytics.mv_airbnb_neighbourhood_summary) AS row_count,
    (SELECT COUNT(*)
       FROM analytics.mv_airbnb_neighbourhood_summary
      WHERE neighbourhood IS NULL) AS null_neighbourhoods,
    (SELECT COUNT(*)
       FROM analytics.mv_airbnb_neighbourhood_summary
      WHERE avg_price < 0 OR median_price < 0) AS bad_prices,
    (SELECT COUNT(*)
       FROM analytics.mv_airbnb_neighbourhood_summary
      WHERE availability_30_rate IS NULL
         OR availability_365_rate IS NULL
         OR availability_30_rate NOT BETWEEN 0 AND 1
         OR availability_365_rate NOT BETWEEN 0 AND 1) AS bad_availability,
    (SELECT COALESCE(SUM(num_listings), 0)
       FROM analytics.mv_airbnb_neighbourhood_summary) AS view_listings,
    (SELECT COUNT(*) FROM core.listing) AS core_listings,
    (SELECT COUNT(*) FROM core.listing WHERE price IS NULL) AS null_price_listings,
    (SELECT COUNT(*) FROM core.listing WHERE price > {price_outlier_threshold}) AS price_outliers;
