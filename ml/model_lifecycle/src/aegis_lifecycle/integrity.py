from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import LifecycleError


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise LifecycleError("artifact_missing", f"Required file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LifecycleError("artifact_missing", f"Required JSON does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError("manifest_invalid", f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LifecycleError("manifest_invalid", f"Expected a JSON object: {path}")
    return value


def require_model_id(manifest: dict[str, Any], expected: str) -> None:
    actual = manifest.get("model_id")
    if actual != expected:
        raise LifecycleError(
            "model_id_mismatch", f"Expected model ID {expected!r}, found {actual!r}."
        )


def require_schema(manifest: dict[str, Any], supported: int = 1) -> None:
    actual = manifest.get("feature_schema_version")
    if actual != supported:
        raise LifecycleError(
            "unsupported_schema",
            f"Feature schema {actual!r} is not supported; expected {supported}.",
        )


def hashes_for(paths: dict[str, Path]) -> dict[str, str]:
    return {name: sha256_file(path) for name, path in sorted(paths.items())}


def verify_hash(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise LifecycleError(
            "artifact_integrity_mismatch",
            f"SHA-256 mismatch for {path}: expected {expected}, found {actual}.",
        )
