"""PII audit table: what happens to every sensitive or identity-linking column."""
from __future__ import annotations

import pandas as pd

_ROWS = [
    ("listing", "listing_id", "entity identifier", "keep as entity key only",
     "needed to define one row per listing; excluded from model inputs"),
    ("listing", "host_id", "direct identifier", "never loaded",
     "replaced by a salted SHA-256 pseudonym (host_key) during ingest"),
    ("listing", "host_key", "pseudonymized identifier", "excluded from the feature table",
     "used inside SQL only to count a host's listings (host_listing_count); never returned"),
    ("listing", "host_name", "direct identifier", "never read",
     "not in the ingest column list, so it never enters memory"),
    ("listing", "license", "direct identifier", "never read",
     "not in the ingest column list"),
    ("listing", "bathrooms_text", "free text", "parsed, then dropped",
     "converted to the numeric `bathrooms`; the text is not in the final table"),
    ("listing", "latitude", "precise location", "excluded from the feature table",
     "stored in core but not used; neighbourhood_name is the location feature"),
    ("listing", "longitude", "precise location", "excluded from the feature table",
     "stored in core but not used; neighbourhood_name is the location feature"),
    ("review", "review_id", "record identifier", "excluded from the feature table",
     "only used to de-duplicate reviews during ingest"),
    ("review", "reviewer_id", "direct identifier", "never loaded",
     "replaced by a salted SHA-256 pseudonym (reviewer_key) during ingest"),
    ("review", "reviewer_key", "pseudonymized identifier", "excluded from the feature table",
     "used inside SQL only to count distinct reviewers; never returned"),
    ("review", "reviewer_name", "direct identifier", "never read",
     "not in the ingest column list"),
    ("review", "comments", "free text", "read only to measure length, then discarded",
     "ingest keeps the integer comment_len; the text is never stored; only aggregates "
     "of comment_len are used as features"),
]


def build_pii_audit() -> pd.DataFrame:
    return pd.DataFrame(
        _ROWS, columns=["table", "column", "pii_type", "decision", "reason"]
    )
