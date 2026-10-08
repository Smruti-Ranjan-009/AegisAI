from __future__ import annotations

from pathlib import Path

from mlflow.tracking import MlflowClient

from .config import LifecycleConfig

ANOMALY_EXPERIMENT = "aegisai-anomaly-detection"
CLASSIFIER_EXPERIMENT = "aegisai-incident-classification"


def ensure_experiment(
    client: MlflowClient, config: LifecycleConfig, name: str
) -> str:
    existing = client.get_experiment_by_name(name)
    if existing is not None:
        return existing.experiment_id
    location = (config.artifact_root / "experiments" / name).resolve()
    location.mkdir(parents=True, exist_ok=True)
    return client.create_experiment(
        name,
        artifact_location=Path(location).as_uri(),
        tags={"project": "AegisAI", "managed_by": "aegis-model-lifecycle"},
    )


def initialize_experiments(
    client: MlflowClient, config: LifecycleConfig
) -> dict[str, str]:
    return {
        ANOMALY_EXPERIMENT: ensure_experiment(client, config, ANOMALY_EXPERIMENT),
        CLASSIFIER_EXPERIMENT: ensure_experiment(client, config, CLASSIFIER_EXPERIMENT),
    }
