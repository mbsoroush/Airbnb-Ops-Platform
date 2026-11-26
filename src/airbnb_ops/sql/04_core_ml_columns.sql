-- Additive migration: columns the feature dataset needs. Safe to run on every ingest.
-- CREATE TABLE IF NOT EXISTS in 00_core_schema.sql never changes an existing table, so these
-- columns are added here instead. All are nullable: files without them load as NULL.
-- No free text is stored anywhere in core: comment_len is only the length of a review comment.
ALTER TABLE core.listing
    ADD COLUMN IF NOT EXISTS bedrooms          numeric(5, 1),
    ADD COLUMN IF NOT EXISTS beds              numeric(5, 1),
    ADD COLUMN IF NOT EXISTS bathrooms_text    text,
    ADD COLUMN IF NOT EXISTS maximum_nights    bigint,
    ADD COLUMN IF NOT EXISTS instant_bookable  boolean,
    ADD COLUMN IF NOT EXISTS host_is_superhost boolean;

ALTER TABLE core.review
    ADD COLUMN IF NOT EXISTS comment_len integer;
