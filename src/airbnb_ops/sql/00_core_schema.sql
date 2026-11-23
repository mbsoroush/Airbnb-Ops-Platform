-- Core schema: cleaned, PII-free tables loaded from Inside Airbnb files.
-- Deliberately only primary keys: query tuning is a separate, measured step.
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.listing (
    listing_id           bigint PRIMARY KEY,
    neighbourhood        text NOT NULL,
    room_type            text,
    property_type        text,
    accommodates         integer,
    price                numeric(12, 2),
    minimum_nights       integer,
    availability_30      integer,
    availability_365     integer,
    number_of_reviews    integer,
    review_scores_rating numeric(4, 2),
    host_key             text NOT NULL,
    latitude             double precision,
    longitude            double precision
);

CREATE TABLE IF NOT EXISTS core.calendar_day (
    listing_id     bigint  NOT NULL REFERENCES core.listing (listing_id),
    date           date    NOT NULL,
    available      boolean NOT NULL,
    minimum_nights bigint,
    maximum_nights bigint,
    PRIMARY KEY (listing_id, date)
);

CREATE TABLE IF NOT EXISTS core.review (
    review_id    bigint PRIMARY KEY,
    listing_id   bigint NOT NULL REFERENCES core.listing (listing_id),
    review_date  date   NOT NULL,
    reviewer_key text   NOT NULL
);
