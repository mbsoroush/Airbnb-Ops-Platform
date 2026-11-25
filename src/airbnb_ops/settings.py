"""Environment-driven settings. Nothing secret is hard-coded."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus


@dataclass(frozen=True)
class DbSettings:
    host: str = "localhost"
    port: int = 5432
    name: str = "airbnb"
    user: str = "airbnb"
    password: str = "airbnb"  # local docker-compose default only; override via env

    @classmethod
    def from_env(cls) -> DbSettings:
        d = cls()
        return cls(
            host=os.getenv("AIRBNB_DB_HOST", d.host),
            port=int(os.getenv("AIRBNB_DB_PORT", d.port)),
            name=os.getenv("AIRBNB_DB_NAME", d.name),
            user=os.getenv("AIRBNB_DB_USER", d.user),
            password=os.getenv("AIRBNB_DB_PASSWORD", d.password),
        )

    @property
    def url(self) -> str:
        return (
            f"postgresql+psycopg2://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.name}"
        )


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE lines from a .env file into the environment.

    Real environment variables win: existing values are never overridden.
    Supports comments, blank lines and optionally quoted values; nothing else.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def reader_user() -> str:
    """Name of the read-only Postgres role used by BI tools."""
    return os.getenv("AIRBNB_READER_USER", "metabase_reader")


def reader_password() -> str | None:
    """Password for the read-only role. No default: it must be provided."""
    return os.getenv("AIRBNB_READER_PASSWORD") or None


def pii_salt() -> str:
    """Salt for pseudonymization. Override in any real deployment."""
    return os.getenv("AIRBNB_PII_SALT", "airbnb-ops")
