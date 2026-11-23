import pandas as pd

from airbnb_ops.pii import DIRECT_PII_COLUMNS, handle_pii, pseudonymize_value


def test_pseudonym_is_stable_and_salted():
    assert pseudonymize_value(901) == pseudonymize_value(901)
    assert pseudonymize_value(901) != pseudonymize_value(902)
    assert pseudonymize_value(901, salt="a") != pseudonymize_value(901, salt="b")


def test_handle_pii_drops_identifiers_and_adds_key():
    df = pd.DataFrame({"host_id": [1, 2], "host_name": ["A", "B"], "price": [10, 20]})
    out = handle_pii(df)
    assert not set(DIRECT_PII_COLUMNS) & set(out.columns)
    assert list(out["host_key"]) == [pseudonymize_value(1), pseudonymize_value(2)]
    assert "host_id" in df.columns  # input is not mutated
