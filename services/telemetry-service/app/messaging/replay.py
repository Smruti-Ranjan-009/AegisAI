from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import KafkaSettings
from .contracts import decode_otlp
from .producer import AcknowledgedProducer

SIGNAL_FILES = {"metrics": "metrics.jsonl", "logs": "logs.jsonl", "traces": "traces.jsonl"}


@dataclass(frozen=True)
class ReplayResult:
    run_id: str
    scenario: str
    label: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def load_replay_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing replay manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"schema_version", "run_id", "scenario", "label", "signals"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError("Replay manifest is missing: " + ", ".join(sorted(missing)))
    if manifest["schema_version"] != 1 or manifest["run_id"] != run_dir.name:
        raise ValueError("Replay manifest version or run_id is invalid")
    for signal, filename in SIGNAL_FILES.items():
        if manifest["signals"].get(signal) != filename:
            raise ValueError(f"Replay manifest must map {signal} to {filename}")
    return manifest


def _validated_records(path: Path, signal: str) -> list[bytes]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Replay signal file is missing or empty: {path}")
    records = []
    for line_number, line in enumerate(path.read_bytes().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            decode_otlp(line, signal)
        except Exception as exc:
            message = f"Invalid {signal} replay record at line {line_number}: {exc}"
            raise ValueError(message) from exc
        records.append(line)
    if not records:
        raise ValueError(f"Replay signal file contains no records: {path}")
    return records


def replay_capture(
    run_dir: Path,
    settings: KafkaSettings,
    *,
    limit: int | None = None,
    producer: AcknowledgedProducer | None = None,
) -> ReplayResult:
    manifest = load_replay_manifest(run_dir)
    validated = {
        signal: _validated_records(run_dir / filename, signal)
        for signal, filename in SIGNAL_FILES.items()
    }
    publisher = producer or AcknowledgedProducer(settings, "aegis-phase1-replay")
    counts = {signal: 0 for signal in SIGNAL_FILES}
    remaining = limit
    try:
        for signal, records in validated.items():
            for payload in records:
                if remaining is not None and remaining <= 0:
                    break
                publisher.publish(
                    settings.raw_topic,
                    payload,
                    key=manifest["run_id"],
                    headers=[
                        ("aegis.event_type", "telemetry.raw"),
                        ("aegis.schema_version", "1"),
                        ("aegis.signal", signal),
                        ("content-type", "application/json"),
                        ("aegis.run_id", manifest["run_id"]),
                        ("aegis.scenario", manifest["scenario"]),
                        ("aegis.label", manifest["label"]),
                    ],
                )
                counts[signal] += 1
                if remaining is not None:
                    remaining -= 1
            if remaining is not None and remaining <= 0:
                break
    finally:
        publisher.flush()
    return ReplayResult(
        run_id=manifest["run_id"],
        scenario=manifest["scenario"],
        label=manifest["label"],
        counts=counts,
    )
