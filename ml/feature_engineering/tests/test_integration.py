from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

from aegis_features.config import BuildConfig
from aegis_features.dataset import build_dataset, dataset_summary, validate_dataset
from aegis_features.errors import DataQualityError


def test_end_to_end_parquet_round_trip_is_deterministic(
    tmp_path, fixture_raw_root, fixture_run_id
) -> None:
    config = BuildConfig(raw_root=fixture_raw_root, output_root=tmp_path / "features")
    first = build_dataset([fixture_run_id], config)
    first_service = pq.read_table(first.dataset_dir / "service_windows.parquet").to_pylist()
    first_metric = pq.read_table(first.dataset_dir / "metric_windows.parquet").to_pylist()
    second = build_dataset([fixture_run_id], config)
    second_service = pq.read_table(second.dataset_dir / "service_windows.parquet").to_pylist()
    second_metric = pq.read_table(second.dataset_dir / "metric_windows.parquet").to_pylist()

    assert first.dataset_id == second.dataset_id
    assert first_service == second_service
    assert first_metric == second_metric
    assert first.manifest["columns"] == second.manifest["columns"]
    assert validate_dataset(first.dataset_dir)["quality_status"] == "PASS"
    summary = dataset_summary(first.dataset_dir)
    assert summary["service_window_rows"] == 1
    assert summary["metric_window_rows"] == 5


def test_validator_does_not_trust_manifest_row_count(
    tmp_path, fixture_raw_root, fixture_run_id
) -> None:
    result = build_dataset(
        [fixture_run_id],
        BuildConfig(raw_root=fixture_raw_root, output_root=tmp_path / "features"),
    )
    manifest_path = result.dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["service_window_rows"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DataQualityError, match="row count"):
        validate_dataset(result.dataset_dir)
