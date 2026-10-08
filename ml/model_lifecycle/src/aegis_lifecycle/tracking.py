from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient

from .config import LifecycleConfig
from .errors import LifecycleError
from .experiments import initialize_experiments

SENSITIVE_TERMS = ("password", "secret", "token", "api_key", "access_key")


def configure_tracking(config: LifecycleConfig) -> MlflowClient:
    config.ensure_directories()
    mlflow.set_tracking_uri(config.tracking_uri)
    try:
        return MlflowClient(tracking_uri=config.tracking_uri)
    except Exception as exc:  # noqa: BLE001 - MLflow backend exceptions vary
        raise LifecycleError("tracking_unavailable", str(exc)) from exc


def initialize(config: LifecycleConfig) -> dict[str, Any]:
    client = configure_tracking(config)
    experiments = initialize_experiments(client, config)
    return {
        "status": "READY",
        "tracking_uri": config.tracking_uri,
        "artifact_root": str(config.artifact_root),
        "experiments": experiments,
    }


def _safe_key(key: str) -> None:
    lowered = key.lower()
    if any(term in lowered for term in SENSITIVE_TERMS):
        raise LifecycleError("sensitive_parameter", f"Refusing to log sensitive key: {key}")


def safe_log_params(values: Mapping[str, Any]) -> None:
    safe: dict[str, Any] = {}
    for key, value in values.items():
        _safe_key(key)
        if value is not None:
            safe[key] = value
    mlflow.log_params(safe)


def safe_tags(values: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        _safe_key(key)
        if value is not None:
            result[key] = str(value)
    return result


def finite_metrics(values: Mapping[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in values.items():
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise LifecycleError("manifest_invalid", f"Metric {key} is not numeric.") from exc
        if not math.isfinite(numeric):
            raise LifecycleError("manifest_invalid", f"Metric {key} is not finite.")
        result[key] = numeric
    return result
