from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from . import __version__
from .config import FEATURE_SCHEMA_VERSION, BuildConfig
from .contracts import feature_columns, metadata_columns, target_columns
from .loaders import RunManifest
from .quality import QualityCounters


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def dataset_manifest(
    *,
    dataset_id: str,
    config: BuildConfig,
    runs: list[RunManifest],
    service_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    counters: QualityCounters,
    source_hashes: dict[str, str],
    source_size_bytes: int,
    build_duration_seconds: float,
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "created_at_utc": utc_now_text(),
        "window_seconds": config.window_seconds,
        "source_run_ids": [run.run_id for run in runs],
        "source_scenarios": sorted({run.scenario for run in runs}),
        "service_window_rows": len(service_rows),
        "metric_window_rows": len(metric_rows),
        "services": sorted({str(row["service_name"]) for row in service_rows}),
        "labels": sorted({run.label for run in runs}),
        "input_records": counters.input_records,
        "duplicate_records_removed": counters.duplicate_records_removed,
        "invalid_observations": counters.missing_timestamp_count,
        "unknown_service_observations": counters.unknown_service_observations,
        "columns": {
            "service_windows": {
                "metadata": list(metadata_columns("service_windows")),
                "targets": list(target_columns("service_windows")),
                "features": list(feature_columns("service_windows")),
            },
            "metric_windows": {
                "metadata": list(metadata_columns("metric_windows")),
                "targets": list(target_columns("metric_windows")),
                "features": list(feature_columns("metric_windows")),
            },
        },
        "libraries": {
            "aegis_feature_engineering": __version__,
            "opentelemetry_proto": version("opentelemetry-proto"),
            "protobuf": version("protobuf"),
            "pyarrow": version("pyarrow"),
        },
        "configuration": {
            "window_seconds": config.window_seconds,
            "max_invalid_observation_ratio": config.max_invalid_observation_ratio,
            "window_convention": "[start, end)",
            "event_time": True,
        },
        "source_hashes_sha256": dict(sorted(source_hashes.items())),
        "source_size_bytes": source_size_bytes,
        "build_duration_seconds": round(build_duration_seconds, 6),
    }


def write_json(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
