import os

from airbnb_ops.settings import load_dotenv


def test_load_dotenv_sets_missing_values_and_never_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())  # keep the real environment clean
    os.environ["DOTENV_TEST_KEEP"] = "from-real-env"
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "DOTENV_TEST_PLAIN=1\n"
        'DOTENV_TEST_QUOTED="two words"\n'
        "DOTENV_TEST_EQUALS = x=y\n"
        "DOTENV_TEST_KEEP=from-file\n"
        "\n"
        "not a valid line\n",
        encoding="utf-8",
    )
    load_dotenv(env)
    assert os.environ["DOTENV_TEST_PLAIN"] == "1"
    assert os.environ["DOTENV_TEST_QUOTED"] == "two words"
    assert os.environ["DOTENV_TEST_EQUALS"] == "x=y"
    assert os.environ["DOTENV_TEST_KEEP"] == "from-real-env"


def test_load_dotenv_ignores_missing_file(tmp_path):
    load_dotenv(tmp_path / "does-not-exist.env")
