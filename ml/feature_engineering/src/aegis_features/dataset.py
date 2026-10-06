from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .aggregation import build_metric_windows, build_service_windows
from .config import FEATURE_SCHEMA_VERSION, KNOWN_SCENARIOS, BuildConfig
from .contracts import feature_columns, ordered_columns
from .errors import DataQualityError, DuplicateConflictError, InputValidationError
from .loaders import SIGNALS, RunManifest, iter_signal_records, load_manifest, source_files
from .manifest import dataset_manifest, write_json
from .observations import LogObservation, MetricObservation, SpanObservation
from .otlp import normalize_record
from .quality import (
    QualityCounters,
    observe,
    quality_report,
    validate_feature_rows,
    validate_observations,
)
from .windows import metric_window_id, service_window_id


@dataclass(frozen=True)
class BuildResult:
    dataset_id: str
    dataset_dir: Path
    manifest: dict[str, Any]
    quality: dict[str, Any]


class SourceDeduplicator:
    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}
        self.duplicates_removed = 0

    def accept(self, source_event_id: str, canonical_payload: bytes) -> bool:
        digest = hashlib.sha256(canonical_payload).hexdigest()
        existing = self._hashes.get(source_event_id)
        if existing is None:
            self._hashes[source_event_id] = digest
            return True
        if existing != digest:
            raise DuplicateConflictError(
                f"Source event ID {source_event_id!r} has conflicting payloads"
            )
        self.duplicates_removed += 1
        return False


def _field(name: str, data_type: pa.DataType, *, nullable: bool = False) -> pa.Field:
    return pa.field(name, data_type, nullable=nullable)


def service_schema() -> pa.Schema:
    count_names = {
        name
        for name in feature_columns("service_windows")
        if name.endswith("_count") or name == "log_body_bytes_max"
    }
    nullable_stats = {
        "log_body_bytes_mean",
        "log_body_bytes_max",
        "span_duration_ms_mean",
        "span_duration_ms_min",
        "span_duration_ms_max",
        "span_duration_ms_p50",
        "span_duration_ms_p95",
        "span_duration_ms_p99",
    }
    fields = [
        _field("feature_schema_version", pa.int16()),
        _field("window_id", pa.string()),
        _field("run_id", pa.string()),
        _field("service_name", pa.string()),
        _field("window_start_utc", pa.timestamp("us", tz="UTC")),
        _field("window_end_utc", pa.timestamp("us", tz="UTC")),
        _field("window_seconds", pa.int32()),
        _field("source_event_count", pa.int64()),
        _field("scenario", pa.string()),
        _field("label", pa.string()),
        _field("is_anomaly", pa.bool_()),
    ]
    for name in feature_columns("service_windows"):
        data_type = pa.int64() if name in count_names else pa.float64()
        fields.append(_field(name, data_type, nullable=name in nullable_stats))
    return pa.schema(fields)


def metric_schema() -> pa.Schema:
    fields = [
        _field("feature_schema_version", pa.int16()),
        _field("metric_window_id", pa.string()),
        _field("run_id", pa.string()),
        _field("service_name", pa.string()),
        _field("window_start_utc", pa.timestamp("us", tz="UTC")),
        _field("window_end_utc", pa.timestamp("us", tz="UTC")),
        _field("window_seconds", pa.int32()),
        _field("metric_name", pa.string()),
        _field("unit", pa.string()),
        _field("metric_type", pa.string()),
        _field("scenario", pa.string()),
        _field("label", pa.string()),
        _field("is_anomaly", pa.bool_()),
    ]
    for name in feature_columns("metric_windows"):
        is_count = name.endswith("_count")
        fields.append(_field(name, pa.int64() if is_count else pa.float64(), nullable=not is_count))
    return pa.schema(fields)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_id(
    runs: list[RunManifest], source_hashes: dict[str, str], config: BuildConfig
) -> str:
    identity = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "run_ids": [run.run_id for run in runs],
        "window_seconds": config.window_seconds,
        "max_invalid_observation_ratio": config.max_invalid_observation_ratio,
        "source_hashes": source_hashes,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return f"phase4-v{FEATURE_SCHEMA_VERSION}-{hashlib.sha256(canonical).hexdigest()[:12]}"


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd", version="2.6")
    temporary.replace(path)


def build_dataset(run_ids: list[str], config: BuildConfig) -> BuildResult:
    started = time.perf_counter()
    if not run_ids:
        raise InputValidationError("At least one --run is required")
    if len(run_ids) != len(set(run_ids)):
        raise InputValidationError("Duplicate run IDs are not allowed")
    runs = [load_manifest(config.raw_root, run_id) for run_id in sorted(run_ids)]
    metrics: list[MetricObservation] = []
    logs: list[LogObservation] = []
    spans: list[SpanObservation] = []
    counters = QualityCounters()
    deduplicator = SourceDeduplicator()
    source_hashes: dict[str, str] = {}
    source_size_bytes = 0

    for run in runs:
        all_source_paths = (run.run_dir / "manifest.json", *source_files(run))
        for source_path in all_source_paths:
            key = f"{run.run_id}/{source_path.name}"
            source_hashes[key] = _hash_file(source_path)
            source_size_bytes += source_path.stat().st_size
        for signal in SIGNALS:
            for record in iter_signal_records(run, signal):
                counters.input_records += 1
                if not deduplicator.accept(record.source_event_id, record.canonical_payload):
                    continue
                batch = normalize_record(record)
                metrics.extend(batch.metrics)
                logs.extend(batch.logs)
                spans.extend(batch.spans)
                observe(counters, "metrics", batch.metrics)
                observe(counters, "logs", batch.logs)
                observe(counters, "traces", batch.spans)

    counters.duplicate_records_removed = deduplicator.duplicates_removed
    validate_observations(counters, config.max_invalid_observation_ratio)
    service_rows = build_service_windows(metrics, logs, spans, config.window_seconds)
    metric_rows = build_metric_windows(metrics, config.window_seconds)
    validate_feature_rows(service_rows, "service_windows")
    validate_feature_rows(metric_rows, "metric_windows")
    if not service_rows:
        raise DataQualityError("No service windows were produced")

    dataset_id = _dataset_id(runs, source_hashes, config)
    dataset_dir = config.output_root / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _write_parquet(dataset_dir / "service_windows.parquet", service_rows, service_schema())
    _write_parquet(dataset_dir / "metric_windows.parquet", metric_rows, metric_schema())
    quality = quality_report(
        counters,
        service_rows,
        metric_rows,
        config.max_invalid_observation_ratio,
    )
    manifest = dataset_manifest(
        dataset_id=dataset_id,
        config=config,
        runs=runs,
        service_rows=service_rows,
        metric_rows=metric_rows,
        counters=counters,
        source_hashes=source_hashes,
        source_size_bytes=source_size_bytes,
        build_duration_seconds=time.perf_counter() - started,
    )
    write_json(dataset_dir / "quality.json", quality)
    write_json(dataset_dir / "manifest.json", manifest)
    validate_dataset(dataset_dir)
    return BuildResult(dataset_id, dataset_dir, manifest, quality)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataQualityError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise DataQualityError(f"Expected JSON object: {path}")
    return document


def _validate_table(
    table: pa.Table,
    dataset: str,
    id_column: str,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_columns = list(ordered_columns(dataset))
    if table.column_names != expected_columns:
        raise DataQualityError(f"{dataset} columns do not match feature catalog v1")
    expected_schema = service_schema() if dataset == "service_windows" else metric_schema()
    if not table.schema.equals(expected_schema, check_metadata=False):
        raise DataQualityError(f"{dataset} Parquet types/nullability do not match schema v1")
    rows = table.to_pylist()
    expected_count = manifest[f"{dataset.removesuffix('s')}_rows"]
    if len(rows) != expected_count:
        raise DataQualityError(f"{dataset} row count does not match manifest")
    identifiers = [row[id_column] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise DataQualityError(f"{dataset} contains duplicate deterministic IDs")
    for row in rows:
        if row["feature_schema_version"] != FEATURE_SCHEMA_VERSION:
            raise DataQualityError(f"{dataset} contains an unsupported schema version")
        if row["scenario"] not in KNOWN_SCENARIOS or row["label"] != row["scenario"]:
            raise DataQualityError(f"{dataset} contains invalid target metadata")
        if row["is_anomaly"] != (row["scenario"] != "normal"):
            raise DataQualityError(f"{dataset} contains inconsistent is_anomaly targets")
    validate_feature_rows(rows, dataset)
    return rows


def validate_dataset(dataset_dir: Path) -> dict[str, Any]:
    manifest = _read_json(dataset_dir / "manifest.json")
    quality = _read_json(dataset_dir / "quality.json")
    if manifest.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise DataQualityError("Manifest feature schema version is not supported")
    if manifest.get("dataset_id") != dataset_dir.name:
        raise DataQualityError("Manifest dataset_id does not match directory name")
    if quality.get("status") != "PASS":
        raise DataQualityError("Dataset quality status is not PASS")
    for dataset in ("service_windows", "metric_windows"):
        declared = manifest.get("columns", {}).get(dataset, {})
        if declared.get("features") != list(feature_columns(dataset)):
            raise DataQualityError(f"Manifest {dataset} feature columns do not match catalog")
        if declared.get("metadata", []) + declared.get("targets", []) + declared.get(
            "features", []
        ) != list(ordered_columns(dataset)):
            raise DataQualityError(f"Manifest {dataset} column roles do not match catalog")
    service_table = pq.read_table(dataset_dir / "service_windows.parquet")
    metric_table = pq.read_table(dataset_dir / "metric_windows.parquet")
    service_rows = _validate_table(
        service_table, "service_windows", "window_id", manifest
    )
    metric_rows = _validate_table(
        metric_table, "metric_windows", "metric_window_id", manifest
    )
    for row in service_rows:
        expected = service_window_id(
            row["run_id"], row["service_name"], row["window_start_utc"], row["window_seconds"]
        )
        if row["window_id"] != expected:
            raise DataQualityError("Service window ID does not match row identity")
    for row in metric_rows:
        expected = metric_window_id(
            row["run_id"],
            row["service_name"],
            row["window_start_utc"],
            row["window_seconds"],
            row["metric_name"],
            row["unit"],
            row["metric_type"],
        )
        if row["metric_window_id"] != expected:
            raise DataQualityError("Metric window ID does not match row identity")
    row_run_ids = sorted({row["run_id"] for row in service_rows})
    if row_run_ids != sorted(manifest["source_run_ids"]):
        raise DataQualityError("Service rows do not cover the manifest source run IDs")
    return dataset_summary(dataset_dir, service_rows=service_rows, manifest=manifest)


def dataset_summary(
    dataset_dir: Path,
    *,
    service_rows: list[dict[str, Any]] | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = manifest or _read_json(dataset_dir / "manifest.json")
    service_rows = service_rows or pq.read_table(
        dataset_dir / "service_windows.parquet"
    ).to_pylist()
    scenarios = Counter(str(row["scenario"]) for row in service_rows)
    labels = Counter(str(row["label"]) for row in service_rows)
    starts = [row["window_start_utc"] for row in service_rows]
    ends = [row["window_end_utc"] for row in service_rows]
    return {
        "dataset_id": manifest["dataset_id"],
        "runs": manifest["source_run_ids"],
        "scenarios": dict(sorted(scenarios.items())),
        "services": manifest["services"],
        "service_window_rows": manifest["service_window_rows"],
        "metric_window_rows": manifest["metric_window_rows"],
        "time_range_utc": [min(starts).isoformat(), max(ends).isoformat()] if starts else [],
        "class_distribution": dict(sorted(labels.items())),
        "service_feature_count": len(feature_columns("service_windows")),
        "metric_feature_count": len(feature_columns("metric_windows")),
        "quality_status": _read_json(dataset_dir / "quality.json")["status"],
    }
