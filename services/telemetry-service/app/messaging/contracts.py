from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .errors import PermanentMessageError

VALID_SIGNALS = ("metrics", "logs", "traces")
ROOT_BY_SIGNAL = {
    "metrics": "resourceMetrics",
    "logs": "resourceLogs",
    "traces": "resourceSpans",
}
REQUIRED_HEADERS = ("aegis.event_type", "aegis.schema_version", "aegis.signal")


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def contracts_directory() -> Path:
    configured = os.getenv("AEGIS_CONTRACTS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "shared/contracts/events"


def kafka_headers(headers: list[tuple[str, bytes | None]] | None) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for key, value in headers or []:
        try:
            result[key] = value.decode("utf-8") if value is not None else None
        except UnicodeDecodeError as exc:
            raise PermanentMessageError(
                "invalid_utf8", f"Kafka header {key!r} is not valid UTF-8"
            ) from exc
    return result


def validate_raw_headers(headers: dict[str, str | None]) -> str:
    missing = [name for name in REQUIRED_HEADERS if not headers.get(name)]
    if missing:
        raise PermanentMessageError(
            "missing_header", "Missing required Kafka header(s): " + ", ".join(missing)
        )
    if headers["aegis.event_type"] != "telemetry.raw":
        raise PermanentMessageError(
            "missing_header", "aegis.event_type must be telemetry.raw"
        )
    if headers["aegis.schema_version"] != "1":
        raise PermanentMessageError(
            "missing_header", "aegis.schema_version must be 1"
        )
    signal = headers["aegis.signal"]
    if signal not in VALID_SIGNALS:
        raise PermanentMessageError("unsupported_signal", f"Unsupported signal: {signal!r}")
    return signal


def decode_otlp(payload: bytes, signal: str) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PermanentMessageError("invalid_utf8", "Kafka value is not valid UTF-8") from exc
    try:
        document = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise PermanentMessageError("invalid_json", f"Kafka value is not JSON: {exc.msg}") from exc
    root = ROOT_BY_SIGNAL[signal]
    if not isinstance(document, dict):
        raise PermanentMessageError(
            "invalid_otlp_structure", "Expected an OTLP JSON object"
        )
    # Protobuf JSON omits empty repeated fields, so an empty export request is
    # canonically encoded as {} rather than {"resourceMetrics": []}, etc.
    document.setdefault(root, [])
    if not isinstance(document[root], list):
        raise PermanentMessageError(
            "invalid_otlp_structure", f"Expected {root} to be an array"
        )
    return document


def extract_service_names(payload: dict[str, Any], signal: str) -> tuple[str, ...]:
    names: set[str] = set()
    for resource_item in payload.get(ROOT_BY_SIGNAL[signal], []):
        if not isinstance(resource_item, dict):
            continue
        resource = resource_item.get("resource")
        if not isinstance(resource, dict):
            continue
        for attribute in resource.get("attributes", []):
            if not isinstance(attribute, dict) or attribute.get("key") != "service.name":
                continue
            value = attribute.get("value")
            if isinstance(value, dict) and isinstance(value.get("stringValue"), str):
                if value["stringValue"]:
                    names.add(value["stringValue"])
    return tuple(sorted(names))


def deterministic_event_id(topic: str, partition: int, offset: int) -> str:
    identity = f"{topic}:{partition}:{offset}".encode()
    return hashlib.sha256(identity).hexdigest()


def ground_truth(headers: dict[str, str | None]) -> dict[str, str | None]:
    return {
        "run_id": headers.get("aegis.run_id"),
        "scenario": headers.get("aegis.scenario"),
        "label": headers.get("aegis.label"),
    }


def build_processed_event(
    *,
    topic: str,
    partition: int,
    offset: int,
    signal: str,
    headers: dict[str, str | None],
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": deterministic_event_id(topic, partition, offset),
        "event_type": "telemetry.processed",
        "produced_at_utc": utc_timestamp(),
        "signal": signal,
        "source": {"topic": topic, "partition": partition, "offset": offset},
        "service_names": list(extract_service_names(payload, signal)),
        "ground_truth": ground_truth(headers),
        "payload": payload,
    }


def load_schema(filename: str) -> dict[str, Any]:
    return json.loads((contracts_directory() / filename).read_text(encoding="utf-8"))


def validate_schema(document: dict[str, Any], filename: str) -> None:
    validator = Draft202012Validator(load_schema(filename), format_checker=FormatChecker())
    try:
        validator.validate(document)
    except ValidationError as exc:
        raise PermanentMessageError(
            "processed_schema_validation", f"Schema validation failed: {exc.message}"
        ) from exc
