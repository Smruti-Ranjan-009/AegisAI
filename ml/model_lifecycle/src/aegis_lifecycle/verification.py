from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient

from .config import LifecycleConfig
from .errors import LifecycleError
from .integrity import verify_hash
from .registry import alias_version, require_upstream_anomaly, spec_for


def _artifact_paths(client: MlflowClient, run_id: str, root: str = "") -> set[str]:
    found: set[str] = set()
    for item in client.list_artifacts(run_id, root):
        found.add(item.path)
        if item.is_dir:
            found.update(_artifact_paths(client, run_id, item.path))
    return found


def _load_example(client: MlflowClient, run_id: str) -> pd.DataFrame:
    local = client.download_artifacts(run_id, "lineage/input_example.json")
    document = json.loads(Path(local).read_text(encoding="utf-8"))
    return pd.DataFrame(document["data"], columns=document["columns"])


def verify_version(
    client: MlflowClient,
    config: LifecycleConfig,
    key: str,
    version_number: str,
    *,
    require_approved: bool = True,
) -> dict[str, Any]:
    spec = spec_for(key)
    try:
        version = client.get_model_version(spec.registered_name, str(version_number))
    except Exception as exc:  # noqa: BLE001 - backend exception types vary
        raise LifecycleError("version_not_found", str(exc)) from exc
    tags = version.tags
    if require_approved and tags.get("validation_status") != "approved":
        raise LifecycleError("promotion_rejected", "Model version is not lifecycle-approved.")
    if tags.get("feature_schema_version") != "1":
        raise LifecycleError("unsupported_schema", "Only feature schema version 1 is supported.")
    artifact_hash = tags.get("artifact_sha256")
    relative_path = tags.get("source_artifact_path")
    if not artifact_hash or not relative_path:
        raise LifecycleError("promotion_rejected", "Model artifact integrity tags are missing.")
    source = (config.repository / relative_path).resolve()
    try:
        source.relative_to(config.repository)
    except ValueError as exc:
        raise LifecycleError(
            "artifact_integrity_mismatch", "Source path escapes repository."
        ) from exc
    verify_hash(source, artifact_hash)
    if not version.run_id:
        raise LifecycleError("promotion_rejected", "Registry version is missing its run ID.")
    run = client.get_run(version.run_id)
    for metric in spec.required_metrics:
        value = run.data.metrics.get(metric)
        if value is None or not math.isfinite(value):
            raise LifecycleError(
                "promotion_rejected", f"Required finite metric is missing: {metric}"
            )
    artifacts = _artifact_paths(client, version.run_id)
    required = {
        "lineage/integrity.json",
        "lineage/model_card.json",
        "lineage/input_example.json",
        "lineage/source/manifest.json",
        "lineage/source/feature_schema.json",
        "lineage/source/split.json",
    }
    missing = sorted(required - artifacts)
    if missing:
        raise LifecycleError(
            "promotion_rejected", f"Required lineage artifacts are missing: {', '.join(missing)}"
        )
    if key == "classifier":
        upstream = tags.get("upstream_anomaly_model_id")
        if not upstream:
            raise LifecycleError("upstream_dependency_missing", "Classifier upstream ID missing.")
        require_upstream_anomaly(client, upstream)
    model_uri = f"models:/{spec.registered_name}/{version.version}"
    model_metadata = mlflow.models.get_model_info(model_uri)
    if model_metadata.signature is None:
        raise LifecycleError("promotion_rejected", "MLflow model signature is missing.")
    try:
        loaded = mlflow.pyfunc.load_model(model_uri)
        prediction = loaded.predict(_load_example(client, version.run_id))
    except Exception as exc:  # noqa: BLE001 - flavor/load failures vary
        raise LifecycleError("promotion_rejected", f"Model smoke inference failed: {exc}") from exc
    if len(prediction) != 1:
        raise LifecycleError("promotion_rejected", "Smoke inference returned the wrong row count.")
    return {
        "status": "PASS",
        "model": key,
        "registered_model": spec.registered_name,
        "version": str(version.version),
        "source_model_id": tags.get("source_model_id"),
        "artifact_sha256": artifact_hash,
        "model_uri": model_uri,
        "signature": model_metadata.signature.to_dict(),
    }


def verify_alias(
    client: MlflowClient, config: LifecycleConfig, key: str, alias: str
) -> dict[str, Any]:
    spec = spec_for(key)
    version = alias_version(client, spec, alias)
    if version is None:
        raise LifecycleError(
            "alias_not_found", f"Alias {alias!r} does not exist for {spec.registered_name}."
        )
    result = verify_version(client, config, key, version.version)
    result["alias"] = alias
    result["model_uri"] = f"models:/{spec.registered_name}@{alias}"
    return result
