"""PII handling: drop direct identifiers, pseudonymize host_id."""
import hashlib

import pandas as pd

DIRECT_PII_COLUMNS = ["host_name", "host_id"]


def pseudonymize_value(value, salt: str = "qbc12") -> str:
    """Return a stable SHA-256 based key (unlike built-in hash(), same across sessions)."""
    raw = f"{salt}:{value}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def handle_pii(df: pd.DataFrame) -> pd.DataFrame:
    """Drop host_name, replace host_id with host_key, drop host_id."""
    out = df.copy()
    if "host_id" in out.columns:
        out["host_key"] = out["host_id"].map(pseudonymize_value)
    present = [c for c in DIRECT_PII_COLUMNS if c in out.columns]
    return out.drop(columns=present)
