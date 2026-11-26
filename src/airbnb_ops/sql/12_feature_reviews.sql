-- One row per listing that has reviews up to and including the cutoff. Aggregated in SQL:
-- raw reviews never go into pandas. Only comment lengths exist, never comment text.
-- days_since_last_review is computed in Python from last_review_date.
SELECT
    listing_id,
    COUNT(*) AS total_reviews_before_cutoff,
    COUNT(DISTINCT reviewer_key) AS unique_reviewers_before_cutoff,
    CAST(AVG(comment_len) AS double precision) AS avg_comment_len_before_cutoff,
    MAX(comment_len) AS max_comment_len_before_cutoff,
    MAX(review_date) AS last_review_date
FROM core.review
WHERE review_date <= CAST(:cutoff_date AS date)
GROUP BY listing_id;
