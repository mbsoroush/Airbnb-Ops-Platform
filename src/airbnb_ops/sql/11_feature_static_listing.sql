-- One row per listing: static attributes. host_key is only used inside this query (to count
-- the host's listings) and is never returned. bathrooms_text is parsed to a number in Python.
SELECT
    l.listing_id,
    l.room_type,
    l.property_type,
    l.neighbourhood AS neighbourhood_name,
    l.accommodates,
    CAST(l.bedrooms AS double precision) AS bedrooms,
    CAST(l.beds AS double precision) AS beds,
    l.bathrooms_text,
    CAST(l.price AS double precision) AS listing_price,
    l.minimum_nights,
    l.maximum_nights,
    l.instant_bookable,
    l.host_is_superhost,
    COUNT(*) OVER (PARTITION BY l.host_key) AS host_listing_count
FROM core.listing AS l;
