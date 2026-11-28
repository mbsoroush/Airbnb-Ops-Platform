"""Environment-driven MLflow settings. Credentials are never stored here.

MLflow itself reads MLFLOW_TRACKING_USERNAME / MLFLOW_TRACKING_PASSWORD from the environment,
which is how a remote server (for example a bootcamp one) can be used without changing code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TRACKING_URI = "http://localhost:5001"
DEFAULT_EXPERIMENT_NAME = "airbnb_high_demand_proxy"


@dataclass(frozen=True)
class MlSettings:
    tracking_uri: str = DEFAULT_TRACKING_URI
    experiment_name: str = DEFAULT_EXPERIMENT_NAME

    @classmethod
    def from_env(cls) -> MlSettings:
        return cls(
            tracking_uri=os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI),
            experiment_name=os.getenv("MLFLOW_EXPERIMENT_NAME", DEFAULT_EXPERIMENT_NAME),
        )
