from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import repository_root
from .errors import AnomalyError


@dataclass(frozen=True)
class FeatureDataset:
    dataset_id: str
    path: Path
    manifest: dict[str, Any]
    service_windows: pa.Table
    metric_windows: pa.Table


def resolve_dataset(value: str | Path, output_root: Path | None = None) -> Path:
    candidate = Path(value)
    root = output_root or repository_root() / "data" / "features"
    return candidate.resolve() if candidate.is_dir() else (root / candidate).resolve()


def load_feature_dataset(value: str | Path, output_root: Path | None = None) -> FeatureDataset:
    path = resolve_dataset(value, output_root)
    manifest_path = path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        service_windows = pq.read_table(path / "service_windows.parquet")
        metric_windows = pq.read_table(path / "metric_windows.parquet")
    except (OSError, json.JSONDecodeError, pa.ArrowException) as exc:
        raise AnomalyError(f"Cannot load Phase 4 feature dataset {path}: {exc}") from exc
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or dataset_id != path.name:
        raise AnomalyError("Feature dataset manifest ID does not match its directory.")
    if manifest.get("feature_schema_version") != 1:
        raise AnomalyError("Phase 5 supports feature_schema_version 1 only.")
    expected = {
        "service_window_rows": service_windows.num_rows,
        "metric_window_rows": metric_windows.num_rows,
    }
    for name, count in expected.items():
        if manifest.get(name) != count:
            raise AnomalyError(f"Feature dataset {name} does not match Parquet row count.")
    return FeatureDataset(dataset_id, path, manifest, service_windows, metric_windows)


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or (
        repository_root() / "ml" / "feature_engineering" / "feature_catalog_v1.json"
    )
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnomalyError(f"Cannot read Phase 4 feature catalog {catalog_path}: {exc}") from exc
    if catalog.get("feature_schema_version") != 1:
        raise AnomalyError("Phase 4 catalog must use feature_schema_version 1.")
    return catalog
