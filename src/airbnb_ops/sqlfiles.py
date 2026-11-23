"""Access to the SQL files shipped inside the package (no database driver needed)."""
from importlib import resources


def load_sql(filename: str) -> str:
    return resources.files("airbnb_ops").joinpath(f"sql/{filename}").read_text("utf-8")
