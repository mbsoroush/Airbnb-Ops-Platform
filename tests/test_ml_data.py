import pytest

from airbnb_ops.features.artifacts import artifact_paths
from airbnb_ops.features.build import build_feature_dataset
from airbnb_ops.features.config import FeatureConfig
from airbnb_ops.ml.data import DatasetIntegrityError, load_dataset
from features_reference import FakeReader, load_core_frames


@pytest.fixture()
def built(mini_city_ml, tmp_path):
    build_feature_dataset(
        FakeReader(load_core_frames(mini_city_ml)), FeatureConfig(dataset_version="t"), tmp_path
    )
    return tmp_path


def test_a_built_dataset_loads_and_is_verified(built):
    dataset = load_dataset(built, "t")
    assert len(dataset.frame) == 24 and dataset.version == "t"
    assert dataset.sha256 and dataset.csv_sha256 == dataset.metadata["files"]["csv"]["sha256"]
    assert dataset.metadata["preprocessing_contract"]["log1p_columns"]


def test_a_changed_file_is_refused(built):
    paths = artifact_paths(built, "t")
    target = paths["parquet"] if paths["parquet"].exists() else paths["csv"]
    if target == paths["csv"]:
        target.write_text(target.read_text().replace("Altstadt", "Altstadt-X", 1))
    else:
        target.write_bytes(target.read_bytes() + b"x")
    with pytest.raises(DatasetIntegrityError, match="changed after it was built"):
        load_dataset(built, "t")


def test_a_missing_dataset_says_how_to_build_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="build-features --version nope"):
        load_dataset(tmp_path, "nope")
