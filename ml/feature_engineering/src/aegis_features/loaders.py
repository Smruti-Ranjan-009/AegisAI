from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import KNOWN_SCENARIOS
from .errors import InputValidationError

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
    "signals",
}


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    scenario: str
    label: str
    run_dir: Path
    raw: dict[str, Any]

    @property
    def is_anomaly(self) -> bool:
        return self.scenario != "normal"


@dataclass(frozen=True)
class SourceRecord:
    run: RunManifest
    signal: str
    source_event_id: str
    document: dict[str, Any]
    canonical_payload: bytes
    line_number: int


def canonical_json(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_run_dir(raw_root: Path, run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise InputValidationError(f"Unsafe or invalid run ID: {run_id!r}")
    root = raw_root.resolve()
    run_dir = (root / run_id).resolve()
    if run_dir.parent != root or not run_dir.is_dir():
        raise InputValidationError(f"Capture run does not exist: {run_id}")
    return run_dir


def load_manifest(raw_root: Path, run_id: str) -> RunManifest:
    run_dir = _safe_run_dir(raw_root, run_id)
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise InputValidationError(f"Required manifest is missing: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError(f"Invalid manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise InputValidationError("Manifest must be a JSON object")
    missing = sorted(REQUIRED_MANIFEST_FIELDS - raw.keys())
    if missing:
        raise InputValidationError("Manifest is missing required fields: " + ", ".join(missing))
    if raw["schema_version"] != 1:
        raise InputValidationError("Unsupported Phase 1 manifest schema_version")
    if raw["run_id"] != run_id:
        raise InputValidationError("Manifest run_id does not match its directory")
    scenario = raw["scenario"]
    label = raw["label"]
    if scenario not in KNOWN_SCENARIOS:
        raise InputValidationError(f"Unknown scenario: {scenario!r}")
    if not isinstance(label, str) or not label or label != scenario:
        raise InputValidationError("Manifest scenario and label must be matching known strings")
    validation_status = raw.get("validation_status")
    if validation_status is not None and validation_status != "PASS":
        raise InputValidationError("Capture manifest validation_status is not PASS")
    if not isinstance(raw["duration_seconds"], int) or raw["duration_seconds"] <= 0:
        raise InputValidationError("Manifest duration_seconds must be positive")
    signals = raw["signals"]
    if not isinstance(signals, dict):
        raise InputValidationError("Manifest signals must be an object")
    for signal, (filename, _) in SIGNALS.items():
        if signals.get(signal) != filename:
            raise InputValidationError(f"Manifest signal {signal!r} must reference {filename!r}")
        signal_path = run_dir / filename
        if not signal_path.is_file() or signal_path.stat().st_size == 0:
            raise InputValidationError(f"Required signal file is missing or empty: {signal_path}")
    return RunManifest(run_id=run_id, scenario=scenario, label=label, run_dir=run_dir, raw=raw)


def iter_signal_records(run: RunManifest, signal: str) -> Iterator[SourceRecord]:
    if signal not in SIGNALS:
        raise ValueError(f"Unsupported signal: {signal}")
    filename, expected_root = SIGNALS[signal]
    path = run.run_dir / filename
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                outer = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise InputValidationError(
                    f"Invalid JSON in {path} at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(outer, dict):
                raise InputValidationError(f"Expected JSON object in {path} at line {line_number}")
            explicit_id = outer.get("event_id")
            document = outer.get("payload") if "payload" in outer else outer
            if not isinstance(document, dict):
                raise InputValidationError(f"OTLP payload is not an object at {path}:{line_number}")
            if expected_root not in document:
                raise InputValidationError(
                    f"Expected OTLP root {expected_root!r} at {path}:{line_number}"
                )
            canonical = canonical_json(document)
            source_id = (
                explicit_id
                if isinstance(explicit_id, str) and explicit_id
                else hashlib.sha256(
                    b"|".join((run.run_id.encode(), signal.encode(), canonical))
                ).hexdigest()
            )
            yield SourceRecord(
                run=run,
                signal=signal,
                source_event_id=source_id,
                document=document,
                canonical_payload=canonical,
                line_number=line_number,
            )


def source_files(run: RunManifest) -> tuple[Path, ...]:
    return tuple(run.run_dir / filename for filename, _ in SIGNALS.values())
