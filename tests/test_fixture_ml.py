"""The committed mini_city_ml CSVs must be exactly what the generator produces."""
import importlib.util
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_committed_fixture_matches_the_generator(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gen", FIXTURES / "make_mini_city_ml.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    monkeypatch.setattr(gen, "OUT", tmp_path)
    gen.generate()
    for name in ("listings.csv", "calendar.csv", "reviews.csv"):
        assert (tmp_path / name).read_bytes() == (FIXTURES / "mini_city_ml" / name).read_bytes()
