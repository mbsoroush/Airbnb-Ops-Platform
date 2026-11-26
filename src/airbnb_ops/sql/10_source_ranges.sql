-- Date ranges of the source tables, used to pick and document the cutoff.
SELECT
    (SELECT MIN(date) FROM core.calendar_day) AS calendar_min_date,
    (SELECT MAX(date) FROM core.calendar_day) AS calendar_max_date,
    (SELECT MIN(review_date) FROM core.review) AS review_min_date,
    (SELECT MAX(review_date) FROM core.review) AS review_max_date;
