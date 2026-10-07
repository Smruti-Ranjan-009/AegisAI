from __future__ import annotations

import hashlib
import json
import platform
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from aegis_anomaly.data import load_feature_dataset

from . import __version__
from .aggregation import aggregate_runs
from .anomaly_adapter import FrozenAnomalyAdapter
from .config import (
    CLASS_NAMES,
    FEATURE_SCHEMA_VERSION,
    FORBIDDEN_FEATURE_FRAGMENTS,
    AggregationConfig,
    repository_root,
)
from .errors import ClassificationError
from .split import ClassificationSplit, build_frozen_split


@dataclass(frozen=True)
class ClassificationDataset:
    dataset_id: str
    path: Path
    manifest: dict[str, Any]
    quality: dict[str, Any]
    table: pa.Table
    split: ClassificationSplit


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or (
        repository_root()
        / "ml"
        / "incident_classification"
        / "feature_catalog_v1.json"
    )
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"Cannot load classification feature catalog: {exc}") from exc
    if catalog.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise ClassificationError("Classification feature catalog must be version 1.")
    assert_safe_feature_names(tuple(catalog.get("predictive_columns", [])))
    return catalog


def assert_safe_feature_names(names: tuple[str, ...]) -> None:
    if not names or len(names) != len(set(names)):
        raise ClassificationError("Predictive feature names must be non-empty and unique.")
    unsafe = [
        name
        for name in names
        if any(fragment in name.lower() for fragment in FORBIDDEN_FEATURE_FRAGMENTS)
    ]
    if unsafe:
        raise ClassificationError("Leakage-bearing predictive features: " + ", ".join(unsafe))


def _schema(feature_names: tuple[str, ...]) -> pa.Schema:
    return pa.schema(
        [
            pa.field("run_id", pa.string(), nullable=False),
            pa.field("scenario", pa.string(), nullable=False),
            pa.field("upstream_feature_dataset_id", pa.string(), nullable=False),
            pa.field("upstream_anomaly_model_id", pa.string(), nullable=False),
            *(pa.field(name, pa.float64(), nullable=False) for name in feature_names),
        ]
    )


def _save_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _campaign_sources(
    path: Path | None,
) -> tuple[set[str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if path is None or not path.is_file():
        return set(), {}, []
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"Cannot load classification campaign result: {exc}") from exc
    if result.get("status") != "PASS":
        raise ClassificationError("Classification campaign result is not PASS.")
    accepted = result.get("accepted_runs")
    if not isinstance(accepted, list):
        raise ClassificationError("Classification campaign accepted_runs is invalid.")
    by_id = {
        str(item["run_id"]): item
        for item in accepted
        if isinstance(item, dict) and isinstance(item.get("run_id"), str)
    }
    new_ids = {run_id for run_id, item in by_id.items() if item.get("source") == "campaign"}
    rejected = result.get("rejected_attempts", [])
    if not isinstance(rejected, list):
        raise ClassificationError("Classification campaign rejected_attempts is invalid.")
    return new_ids, by_id, rejected


def build_classification_dataset(
    feature_dataset: str | Path,
    *,
    anomaly_artifact_root: Path | None = None,
    feature_root: Path | None = None,
    output_root: Path | None = None,
    campaign_result: Path | None = None,
    aggregation: AggregationConfig | None = None,
) -> ClassificationDataset:
    started = time.perf_counter()
    aggregation = aggregation or AggregationConfig()
    upstream = load_feature_dataset(feature_dataset, feature_root)
    adapter = FrozenAnomalyAdapter(artifact_root=anomaly_artifact_root)
    scored = adapter.score(upstream)
    rows = aggregate_runs(scored, aggregation)
    catalog = load_catalog()
    feature_names = tuple(catalog["predictive_columns"])
    run_scenarios = {str(row["run_id"]): str(row["scenario"]) for row in rows}
    if set(run_scenarios.values()) != set(CLASS_NAMES):
        raise ClassificationError(
            "Classification source must contain exactly the five fault classes."
        )
    new_run_ids, campaign_entries, rejected_attempts = _campaign_sources(campaign_result)
    if campaign_entries and set(campaign_entries) != set(run_scenarios):
        raise ClassificationError("Campaign accepted runs do not match Phase 4 feature runs.")
    split = build_frozen_split(run_scenarios, new_run_ids)
    payload = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "upstream_feature_dataset_id": upstream.dataset_id,
        "upstream_anomaly_model_id": adapter.model_id,
        "source_run_ids": sorted(run_scenarios),
        "feature_names": feature_names,
        "top_k": aggregation.top_k,
        "split": split.as_dict(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    dataset_id = "classification-v1-" + hashlib.sha256(encoded).hexdigest()[:12]
    root = output_root or repository_root() / "data" / "classification"
    path = root / dataset_id
    path.mkdir(parents=True, exist_ok=True)
    output_rows = [
        {
            "run_id": row["run_id"],
            "scenario": row["scenario"],
            "upstream_feature_dataset_id": upstream.dataset_id,
            "upstream_anomaly_model_id": adapter.model_id,
            **{name: float(row[name]) for name in feature_names},
        }
        for row in rows
    ]
    table = pa.Table.from_pylist(output_rows, schema=_schema(feature_names))
    pq.write_table(table, path / "incident_runs.parquet", compression="zstd")
    counts = Counter(run_scenarios.values())
    manifest = {
        "dataset_id": dataset_id,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "upstream_feature_dataset_id": upstream.dataset_id,
        "upstream_anomaly_model_id": adapter.model_id,
        "source_run_ids": sorted(run_scenarios),
        "new_campaign_run_ids": sorted(new_run_ids),
        "scenario_counts": {name: counts[name] for name in CLASS_NAMES},
        "row_count": table.num_rows,
        "feature_names": list(feature_names),
        "class_names": list(CLASS_NAMES),
        "capture_configuration": {
            "warmup_seconds": 20,
            "capture_seconds": 60,
            "fault_propagation_seconds": 7,
            "collector_flush_seconds": 3,
            "cooldown_seconds": 15,
        },
        "aggregation_configuration": {
            "top_k": aggregation.top_k,
            "ranking": "anomaly_score descending; window start, service, window ID tie-break",
        },
        "excluded_runs": rejected_attempts,
        "frozen_split": split.as_dict(),
        "anomaly_scored_window_count": len(scored),
        "anomaly_threshold": adapter.threshold,
        "excluded_services": adapter.manifest["excluded_services"],
        "generation_duration_seconds": time.perf_counter() - started,
        "libraries": {
            "aegis_incident_classification": __version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pyarrow": pa.__version__,
        },
    }
    quality = validate_table(table, manifest, feature_names)
    _save_json(path / "manifest.json", manifest)
    _save_json(path / "quality.json", quality)
    _save_json(path / "split.json", split.as_dict())
    return load_classification_dataset(dataset_id, root)


def validate_table(
    table: pa.Table, manifest: dict[str, Any], feature_names: tuple[str, ...]
) -> dict[str, Any]:
    errors: list[str] = []
    rows = table.to_pylist()
    run_ids = [str(row["run_id"]) for row in rows]
    if len(run_ids) != len(set(run_ids)):
        errors.append("Dataset must contain exactly one unique row per run.")
    if table.num_rows != manifest.get("row_count"):
        errors.append("Manifest row count does not match Parquet.")
    if tuple(manifest.get("feature_names", [])) != feature_names:
        errors.append("Manifest feature order does not match catalog.")
    scenarios = Counter(str(row["scenario"]) for row in rows)
    if set(scenarios) != set(CLASS_NAMES):
        errors.append("Dataset must contain exactly the five supported classes.")
    for scenario in CLASS_NAMES:
        if scenarios[scenario] < 6:
            errors.append(f"{scenario} requires at least 6 runs; found {scenarios[scenario]}.")
    matrix = np.asarray([[float(row[name]) for name in feature_names] for row in rows])
    finite = bool(
        matrix.ndim == 2
        and matrix.shape[1] == len(feature_names)
        and np.all(np.isfinite(matrix))
    )
    if not finite:
        errors.append("Predictive matrix must be finite and match the catalog.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "row_count": table.num_rows,
        "unique_run_count": len(set(run_ids)),
        "scenario_counts": dict(sorted(scenarios.items())),
        "finite_predictive_features": finite,
    }


def resolve_dataset(value: str | Path, root: Path | None = None) -> Path:
    candidate = Path(value)
    base = root or repository_root() / "data" / "classification"
    return candidate.resolve() if candidate.is_dir() else (base / candidate).resolve()


def load_classification_dataset(
    value: str | Path, root: Path | None = None
) -> ClassificationDataset:
    path = resolve_dataset(value, root)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        quality = json.loads((path / "quality.json").read_text(encoding="utf-8"))
        split_data = json.loads((path / "split.json").read_text(encoding="utf-8"))
        table = pq.read_table(path / "incident_runs.parquet")
    except (OSError, json.JSONDecodeError, pa.ArrowException) as exc:
        raise ClassificationError(f"Cannot load classification dataset {path}: {exc}") from exc
    if manifest.get("dataset_id") != path.name:
        raise ClassificationError("Classification dataset ID does not match its directory.")
    feature_names = tuple(manifest.get("feature_names", []))
    if table.schema != _schema(feature_names):
        raise ClassificationError("Classification Parquet schema does not match its catalog.")
    validation = validate_table(table, manifest, feature_names)
    if validation["status"] != "PASS" or quality.get("status") != "PASS":
        raise ClassificationError("Classification dataset quality validation failed.")
    split = ClassificationSplit(
        tuple(split_data["development_run_ids"]),
        tuple(split_data["test_run_ids"]),
        int(split_data["random_state"]),
    )
    run_scenarios = {row["run_id"]: row["scenario"] for row in table.to_pylist()}
    split.validate(run_scenarios)
    return ClassificationDataset(path.name, path, manifest, quality, table, split)
