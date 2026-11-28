-- Group labels for the host-grouped comparison. host_key never leaves the database: it is
-- replaced by a dense integer rank. The labels only say which listings share a host; they are
-- kept in memory for one run, never logged as an artifact and never committed.
SELECT
    listing_id,
    DENSE_RANK() OVER (ORDER BY host_key) AS host_group
FROM core.listing;
