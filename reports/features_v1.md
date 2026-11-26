# Feature dataset v1

- Cutoff: **2026-12-24** (earliest_valid): Earliest valid cutoff (calendar start + 90 days), derived from the data.
- History window: 2026-09-26 to 2026-12-24; label window: after 2026-12-24 up to 2027-01-23
- Valid cutoff range in the data: 2026-12-24 to 2027-08-26
- Rows: 7458; positive rate: 0.5748
- Validation: passed

## Target

high_demand_proxy = 1 when future_available_rate_30d <= label_threshold. The rate is the share of days after the cutoff (30 day window) that the calendar marks as available. A day is unavailable when it is booked OR blocked by the host, so this is a low-availability proxy, not confirmed booking demand.

## Source inspection

- Database connection: ok (database `airbnb`, server 16.16 (Debian 16.16-1.pgdg13+1))
- Calendar price: core.calendar_day has no price or adjusted_price column (the Munich calendar file has none), so no calendar price features are built. listing_price comes from core.listing.

| table | columns |
| --- | --- |
| calendar_day | listing_id, date, available, minimum_nights, maximum_nights |
| listing | listing_id, neighbourhood, room_type, property_type, accommodates, price, minimum_nights, availability_30, availability_365, number_of_reviews, review_scores_rating, host_key, latitude, longitude, bedrooms, beds, bathrooms_text, maximum_nights, instant_bookable, host_is_superhost |
| review | review_id, listing_id, review_date, reviewer_key, comment_len |

| measure | count |
| --- | --- |
| listing_rows | 7493 |
| calendar_day_rows | 2734952 |
| review_rows | 247636 |
| listing_null_price | 2413 |
| listing_null_bedrooms | 4 |
| listing_null_beds | 158 |
| listing_null_bathrooms_text | 11 |
| listing_null_maximum_nights | 35 |
| listing_null_instant_bookable | 7493 |
| listing_null_host_is_superhost | 0 |
| calendar_null_available | 0 |
| review_null_comment_len | 24 |

## Row counts and missing-value rules applied

| step | rows |
| --- | --- |
| listings_in_core | 7493 |
| filled_room_type_unknown | 0 |
| filled_property_type_unknown | 0 |
| filled_instant_bookable_false | 7493 |
| filled_host_is_superhost_false | 0 |
| dropped_missing_accommodates | 0 |
| dropped_missing_minimum_nights | 35 |
| dropped_missing_maximum_nights | 0 |
| listings_without_reviews | 1595 |
| dropped_no_calendar_history | 0 |
| dropped_incomplete_history_window | 0 |
| dropped_no_label_window | 0 |
| dropped_incomplete_label_window | 0 |
| rows_final | 7458 |
| dropped_unusable_columns | 0 |

## Validation checks

| check | result |
| --- | --- |
| has_rows | pass |
| column_contract | pass |
| no_duplicate_listing_cutoff | pass |
| no_forbidden_columns | pass |
| no_future_leakage_in_model_inputs | pass |
| model_inputs_match_contract | pass |
| target_not_missing | pass |
| target_is_binary | pass |
| both_classes_present | pass |
| label_window_complete | pass |
| future_rate_consistent | pass |
| label_matches_rule | pass |
| rates_in_unit_interval | pass |
| counts_non_negative | pass |
| window_counts_within_window | pass |
| days_since_review_non_negative | pass |
| cutoff_and_version_constant | pass |

## Label distribution

| high_demand_proxy | count | percentage |
| --- | --- | --- |
| 0 | 3171 | 0.4252 |
| 1 | 4287 | 0.5748 |

## Limitations

- Inside Airbnb's calendar is a forward-looking snapshot: it starts at the scrape date, so the history window and the label window both describe the future as seen on that one day. The history features were not observed before the cutoff in a real-time sense, and this is not a true temporal split (that would need several snapshots).
- The label is a proxy: unavailable means booked or blocked by the host. Far-future dates and holiday periods contain many host blocks, so the label partly reflects host behaviour, not demand.
- Reviews end at the snapshot date, which is before any valid cutoff. The review features are therefore identical for every valid cutoff, and days_since_last_review differs between cutoffs only by a constant shift.
- Datasets built from different cutoffs contain the same listings, so they are not independent evidence for each other.

## Warnings

- WARNING: contract columns ['instant_bookable'] are constant or more than 95% missing, so they carry no signal. They are kept only because the column contract is fixed.

## Files

| file | bytes | sha256 |
| --- | --- | --- |
| listing_availability_features_v1.csv | 1603753 | 3601ff3f44bb7ca544648e208873fbd97be404408186a092177e92509cc73d23 |
| listing_availability_features_v1.parquet | 300107 | 91973b94781b4d25f61f2f1496250ab8987649335164b51b648d36aaa714f6ba |
