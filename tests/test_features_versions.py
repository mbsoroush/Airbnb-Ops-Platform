from datetime import date

from airbnb_ops.features.versions import DATASET_PRESETS, resolve_config


def test_v1_uses_the_derived_cutoff():
    cfg = resolve_config("v1")
    assert cfg.cutoff_date is None and cfg.cutoff_reason is None and cfg.dataset_version == "v1"


def test_v2_preset_is_the_single_source_for_cutoff_and_reason():
    cfg = resolve_config("v2")
    assert cfg.cutoff_date == date(2027, 2, 22)
    assert "Christmas" in cfg.cutoff_reason and "not chosen by model score" in cfg.cutoff_reason
    assert cfg.cutoff_date == DATASET_PRESETS["v2"]["cutoff_date"]


def test_an_explicit_cutoff_overrides_the_preset_and_drops_its_reason():
    cfg = resolve_config("v2", cutoff=date(2027, 3, 1))
    assert cfg.cutoff_date == date(2027, 3, 1) and cfg.cutoff_reason is None
    cfg = resolve_config("v2", cutoff=date(2027, 3, 1), cutoff_reason="because")
    assert cfg.cutoff_reason == "because"


def test_unknown_versions_and_thresholds_pass_through():
    cfg = resolve_config("ci", threshold=0.25)
    assert cfg.dataset_version == "ci" and cfg.cutoff_date is None
    assert cfg.label_threshold == 0.25
