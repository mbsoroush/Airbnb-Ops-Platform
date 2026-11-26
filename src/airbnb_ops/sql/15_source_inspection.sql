-- Connection check, table sizes and missing values of the source tables, for the build report.
SELECT
    current_database() AS database_name,
    current_setting('server_version') AS server_version,
    (SELECT COUNT(*) FROM core.listing) AS listing_rows,
    (SELECT COUNT(*) FROM core.calendar_day) AS calendar_day_rows,
    (SELECT COUNT(*) FROM core.review) AS review_rows,
    (SELECT COUNT(*) FROM core.listing WHERE price IS NULL) AS listing_null_price,
    (SELECT COUNT(*) FROM core.listing WHERE bedrooms IS NULL) AS listing_null_bedrooms,
    (SELECT COUNT(*) FROM core.listing WHERE beds IS NULL) AS listing_null_beds,
    (SELECT COUNT(*) FROM core.listing WHERE bathrooms_text IS NULL) AS listing_null_bathrooms_text,
    (SELECT COUNT(*) FROM core.listing WHERE maximum_nights IS NULL) AS listing_null_maximum_nights,
    (SELECT COUNT(*) FROM core.listing WHERE instant_bookable IS NULL)
        AS listing_null_instant_bookable,
    (SELECT COUNT(*) FROM core.listing WHERE host_is_superhost IS NULL)
        AS listing_null_host_is_superhost,
    (SELECT COUNT(*) FROM core.calendar_day WHERE available IS NULL) AS calendar_null_available,
    (SELECT COUNT(*) FROM core.review WHERE comment_len IS NULL) AS review_null_comment_len;
