from __future__ import annotations

from typing import Any

from mlflow.tracking import MlflowClient

from .audit import append_event
from .config import LifecycleConfig
from .registry import alias_version, spec_for
from .verification import verify_version


def _move_champion(
    client: MlflowClient,
    config: LifecycleConfig,
    key: str,
    version: str,
    reason: str,
    action: str,
) -> dict[str, Any]:
    spec = spec_for(key)
    validation = verify_version(client, config, key, str(version))
    current = alias_version(client, spec, "champion")
    previous = str(current.version) if current is not None else None
    if current is not None and str(current.version) != str(version):
        client.set_registered_model_alias(
            spec.registered_name, "previous_champion", str(current.version)
        )
        client.set_model_version_tag(
            spec.registered_name, str(current.version), "lifecycle_status", "previous_champion"
        )
    client.set_registered_model_alias(spec.registered_name, "champion", str(version))
    client.set_model_version_tag(
        spec.registered_name, str(version), "lifecycle_status", "champion"
    )
    event = append_event(
        config,
        {
            "action": action,
            "model": key,
            "registered_model": spec.registered_name,
            "previous_champion": previous,
            "new_champion": str(version),
            "validation_result": validation["status"],
            "reason": reason,
        },
    )
    return {"status": "PROMOTED", "validation": validation, "audit_event": event}


def promote(
    client: MlflowClient,
    config: LifecycleConfig,
    key: str,
    version: str,
    reason: str = "",
) -> dict[str, Any]:
    return _move_champion(client, config, key, version, reason, "promote")


def rollback(
    client: MlflowClient,
    config: LifecycleConfig,
    key: str,
    version: str,
    reason: str = "",
) -> dict[str, Any]:
    return _move_champion(client, config, key, version, reason, "rollback")
