from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import mlflow
import pandas as pd
import pytest
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import Pipeline

from aegis_lifecycle.config import LifecycleConfig, sqlite_uri
from aegis_lifecycle.experiments import ensure_experiment
from aegis_lifecycle.integrity import sha256_file
from aegis_lifecycle.registry import ModelSpec, ensure_registered_model, spec_for
from aegis_lifecycle.tracking import configure_tracking, initialize


@pytest.fixture
def lifecycle_config(tmp_path: Path) -> LifecycleConfig:
    repository = tmp_path / "repository"
    runtime = repository / ".runtime" / "mlflow"
    database = runtime / "mlflow.db"
    return LifecycleConfig(
        repository=repository,
        runtime_root=runtime,
        database_path=database,
        artifact_root=runtime / "artifacts",
        tracking_uri=sqlite_uri(database),
        audit_path=runtime / "audit.jsonl",
    )


@pytest.fixture
def lifecycle_client(lifecycle_config: LifecycleConfig) -> MlflowClient:
    initialize(lifecycle_config)
    return configure_tracking(lifecycle_config)


def log_fixture_version(
    config: LifecycleConfig,
    client: MlflowClient,
    key: str,
    source_model_id: str,
    *,
    approved: bool = True,
    upstream_anomaly_model_id: str | None = None,
    missing_metric: str | None = None,
    schema_version: str = "1",
) -> Any:
    spec: ModelSpec = spec_for(key)
    ensure_registered_model(client, spec)
    source_dir = config.repository / "artifacts" / "fixtures" / source_model_id
    source_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / "model.joblib"
    joblib.dump({"source_model_id": source_model_id}, source)
    experiment_id = ensure_experiment(client, config, spec.experiment_name)
    example = pd.DataFrame([[0.0]], columns=["feature"])
    model = Pipeline([("classifier", DummyClassifier(strategy="constant", constant=0))])
    model.fit(example, [0])
    with mlflow.start_run(experiment_id=experiment_id):
        for metric in spec.required_metrics:
            if metric != missing_metric:
                mlflow.log_metric(metric, 0.5)
        for name in (
            "integrity.json",
            "model_card.json",
            "input_example.json",
        ):
            payload = (
                {"columns": ["feature"], "data": [[0.0]]}
                if name == "input_example.json"
                else {"fixture": True}
            )
            mlflow.log_dict(payload, f"lineage/{name}")
        for name in ("manifest.json", "feature_schema.json", "split.json"):
            mlflow.log_dict({"fixture": True}, f"lineage/source/{name}")
        model_info = mlflow.sklearn.log_model(
            model,
            name="model",
            signature=infer_signature(example, model.predict(example)),
            input_example=example,
            pip_requirements=["mlflow==3.17.0", "scikit-learn==1.9.0"],
        )
    tags = {
        "project": "AegisAI",
        "phase": spec.phase,
        "task": spec.task,
        "source_model_id": source_model_id,
        "source_dataset_id": "fixture-dataset",
        "source_artifact_path": source.relative_to(config.repository).as_posix(),
        "artifact_sha256": sha256_file(source),
        "feature_schema_version": schema_version,
        "validation_status": "approved" if approved else "pending",
        "lifecycle_status": "candidate",
    }
    if upstream_anomaly_model_id:
        tags["upstream_anomaly_model_id"] = upstream_anomaly_model_id
    version = mlflow.register_model(
        model_info.model_uri, spec.registered_name, tags=tags, await_registration_for=60
    )
    for tag, value in tags.items():
        client.set_model_version_tag(spec.registered_name, version.version, tag, value)
    return client.get_model_version(spec.registered_name, version.version)
