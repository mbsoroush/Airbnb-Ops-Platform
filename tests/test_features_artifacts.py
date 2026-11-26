import json

import pandas as pd
import pytest

from airbnb_ops.features.artifacts import (
    VersionExistsError,
    artifact_paths,
    check_version_free,
    csv_bytes,
    sha256_bytes,
)
from airbnb_ops.features.audit import build_pii_audit
from airbnb_ops.features.config import FORBIDDEN_TABLE_COLUMNS
from airbnb_ops.features.report import render_markdown


def test_artifact_names_follow_the_assignment_contract(tmp_path):
    paths = artifact_paths(tmp_path, "v1")
    assert paths["csv"].name == "listing_availability_features_v1.csv"
    assert paths["parquet"].name == "listing_availability_features_v1.parquet"
    assert paths["metadata"].name == "listing_availability_features_v1_metadata.json"
    assert paths["validation"].name == "listing_availability_features_v1_validation_report.json"
    assert paths["pii_audit"].name == "pii_audit_v1.csv"


def test_csv_bytes_are_deterministic():
    df = pd.DataFrame({"a": [1, 2], "b": [0.5, None]})
    assert csv_bytes(df) == csv_bytes(df.copy())
    assert sha256_bytes(csv_bytes(df)) == sha256_bytes(csv_bytes(df.copy()))


def test_version_check_allows_new_same_and_overwrite_but_not_different(tmp_path):
    paths = artifact_paths(tmp_path, "v1")
    check_version_free(paths, "aaa", overwrite=False)  # nothing exists yet
    paths["metadata"].write_text(json.dumps({"files": {"csv": {"sha256": "aaa"}}}))
    check_version_free(paths, "aaa", overwrite=False)  # identical content
    with pytest.raises(VersionExistsError):
        check_version_free(paths, "bbb", overwrite=False)
    check_version_free(paths, "bbb", overwrite=True)


def test_pii_audit_covers_every_forbidden_table_column():
    audit = build_pii_audit()
    assert set(FORBIDDEN_TABLE_COLUMNS) - {"host_pseudo_id", "reviewer_pseudo_id"} <= set(
        audit["column"]
    )
    assert not audit["decision"].str.contains("keep as model input").any()
    comments = audit[audit["column"] == "comments"].iloc[0]
    assert "discarded" in comments["decision"]


def test_markdown_report_has_the_key_sections():
    meta = {
        "dataset_version": "v1",
        "cutoff": {"cutoff_date": "2026-12-24", "selection_rule": "earliest_valid",
                   "selection_reason": "r", "history_start_date": "a", "label_end_date": "b",
                   "earliest_valid_cutoff": "c", "latest_valid_cutoff": "d"},
        "target_definition": "t", "row_counts": {"rows_final": 3}, "limitations": ["l1"],
        "files": {"csv": {"name": "f.csv", "bytes": 1, "sha256": "x"}, "parquet": None},
    }
    val = {"passed": True, "n_rows": 3, "warnings": [], "checks": {"has_rows": True},
           "label_distribution": [{"high_demand_proxy": 1, "count": 2, "percentage": 0.66}]}
    text = render_markdown(meta, val)
    for needle in ("# Feature dataset v1", "## Limitations", "has_rows", "f.csv", "0.66"):
        assert needle in text
