"""Environment-driven settings. Nothing secret is hard-coded."""
from __future__ import annotations

import os
from dataclasses import dataclass
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


def pii_salt() -> str:
    """Salt for pseudonymization. Override in any real deployment."""
    return os.getenv("AIRBNB_PII_SALT", "airbnb-ops")
