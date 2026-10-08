from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from mlflow.tracking import MlflowClient

from .config import LifecycleConfig
from .registry import SPECS, alias_version, versions


def append_event(config: LifecycleConfig, event: dict[str, Any]) -> dict[str, Any]:
    config.ensure_directories()
    record = {"timestamp_utc": datetime.now(UTC).isoformat(), **event}
    with config.audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_events(config: LifecycleConfig) -> list[dict[str, Any]]:
    if not config.audit_path.is_file():
        return []
    return [
        json.loads(line)
        for line in config.audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def registry_audit(client: MlflowClient, config: LifecycleConfig) -> dict[str, Any]:
    models: list[dict[str, Any]] = []
    for key, spec in SPECS.items():
        candidate = alias_version(client, spec, "candidate")
        champion = alias_version(client, spec, "champion")
        for version in sorted(versions(client, spec), key=lambda item: int(item.version)):
            full = client.get_model_version(spec.registered_name, version.version)
            models.append(
                {
                    "model": key,
                    "registered_model": spec.registered_name,
                    "version": str(full.version),
                    "source_model_id": full.tags.get("source_model_id"),
                    "source_dataset_id": full.tags.get("source_dataset_id"),
                    "artifact_sha256": full.tags.get("artifact_sha256"),
                    "validation_status": full.tags.get("validation_status"),
                    "lifecycle_status": full.tags.get("lifecycle_status"),
                    "upstream_anomaly_model_id": full.tags.get("upstream_anomaly_model_id"),
                    "candidate": bool(candidate and candidate.version == full.version),
                    "champion": bool(champion and champion.version == full.version),
                }
            )
    return {"models": models, "events": read_events(config)}
