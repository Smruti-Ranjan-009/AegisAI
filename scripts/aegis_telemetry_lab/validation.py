from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import LabError

RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?-[0-9a-f]{6}$")
SIGNALS = {
    "metrics": ("metrics.jsonl", "resourceMetrics"),
    "logs": ("logs.jsonl", "resourceLogs"),
    "traces": ("traces.jsonl", "resourceSpans"),
}
REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "run_id",
    "scenario",
    "label",
    "started_at_utc",
    "ended_at_utc",
    "duration_seconds",
    "otel_demo_version",
    "upstream_git_commit",
    "feature_flag",
    "expected_affected_services",
    "signals",
}


@dataclass(frozen=True)
class SignalValidation:
    batches: int
    services: tuple[str, ...]


@dataclass(frozen=True)
class CaptureValidation:
    run_id: str
    scenario: str
    label: str
    signals: dict[str, SignalValidation]
    services: tuple[str, ...]


def is_safe_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


def resolve_run_directory(raw_root: Path, run_id: str, *, must_exist: bool = False) -> Path:
    if not is_safe_run_id(run_id):
        raise LabError(f"Unsafe or invalid run ID: {run_id!r}")
    root = raw_root.resolve()
    candidate = (root / run_id).resolve()
    if candidate.parent != root:
        raise LabError(f"Run path escapes raw dataset directory: {run_id!r}")
    if must_exist and not candidate.is_dir():
        raise LabError(f"Capture run does not exist: {run_id}")
    return candidate


def _attribute_string(attribute: dict[str, Any]) -> str | None:
    value = attribute.get("value")
    if not isinstance(value, dict):
        return None
    string_value = value.get("stringValue")
    return string_value if isinstance(string_value, str) else None


def _services_from_batch(batch: dict[str, Any], root_key: str) -> set[str]:
    services: set[str] = set()
    resources = batch.get(root_key)
    if not isinstance(resources, list):
        return services
    for resource_item in resources:
        if not isinstance(resource_item, dict):
            continue
        resource = resource_item.get("resource")
        if not isinstance(resource, dict):
            continue
        attributes = resource.get("attributes")
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if isinstance(attribute, dict) and attribute.get("key") == "service.name":
                service = _attribute_string(attribute)
                if service:
                    services.add(service)
    return services


def validate_jsonl(path: Path, expected_root_key: str) -> SignalValidation:
    if not path.is_file():
        raise LabError(f"Required signal file is missing: {path}")
    if path.stat().st_size == 0:
        raise LabError(f"Required signal file is empty: {path}")

    batches = 0
    services: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    batch = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LabError(f"Invalid JSON in {path} at line {line_number}: {exc}") from exc
                if not isinstance(batch, dict) or not isinstance(
                    batch.get(expected_root_key), list
                ):
                    raise LabError(
                        f"Unexpected OTLP structure in {path} at line {line_number}; "
                        f"expected {expected_root_key!r}."
                    )
                batches += 1
                services.update(_services_from_batch(batch, expected_root_key))
    except OSError as exc:
        raise LabError(f"Cannot read signal file {path}: {exc}") from exc

    if batches == 0:
        raise LabError(f"Signal file contains no JSON batches: {path}")
    return SignalValidation(batches=batches, services=tuple(sorted(services)))


def validate_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LabError(f"Required manifest is missing: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"Invalid manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise LabError(f"Manifest must be a JSON object: {path}")
    missing = sorted(REQUIRED_MANIFEST_FIELDS - manifest.keys())
    if missing:
        raise LabError(f"Manifest is missing required fields: {', '.join(missing)}")
    if manifest["schema_version"] != 1:
        raise LabError("Unsupported manifest schema_version; expected 1.")
    if not isinstance(manifest["run_id"], str) or not is_safe_run_id(manifest["run_id"]):
        raise LabError("Manifest contains an invalid run_id.")
    if not isinstance(manifest["duration_seconds"], int) or manifest["duration_seconds"] < 1:
        raise LabError("Manifest duration_seconds must be a positive integer.")
    signals = manifest["signals"]
    if not isinstance(signals, dict):
        raise LabError("Manifest signals must be an object.")
    for signal, (filename, _) in SIGNALS.items():
        if signals.get(signal) != filename:
            raise LabError(f"Manifest signal {signal!r} must reference {filename!r}.")
    return manifest


def validate_capture(run_dir: Path) -> CaptureValidation:
    manifest = validate_manifest(run_dir / "manifest.json")
    if manifest["run_id"] != run_dir.name:
        raise LabError("Manifest run_id does not match its directory name.")

    signal_results = {
        signal: validate_jsonl(run_dir / filename, root_key)
        for signal, (filename, root_key) in SIGNALS.items()
    }
    services = tuple(
        sorted({service for result in signal_results.values() for service in result.services})
    )
    if not services:
        raise LabError("No service.name resource attributes were found in captured telemetry.")

    expected = manifest["expected_affected_services"]
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        raise LabError("Manifest expected_affected_services must be an array of strings.")
    missing_expected = sorted(set(expected) - set(services))
    if missing_expected:
        raise LabError(
            "Expected affected services were not observed in telemetry: "
            + ", ".join(missing_expected)
        )

    return CaptureValidation(
        run_id=manifest["run_id"],
        scenario=manifest["scenario"],
        label=manifest["label"],
        signals=signal_results,
        services=services,
    )
