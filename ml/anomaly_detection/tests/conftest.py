from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from aegis_anomaly.data import FeatureDataset, load_catalog, load_feature_dataset

RUNS = {
    "normal": [f"20260101T00000{i}Z-normal-a0000{i}" for i in range(6)],
    "cpu_saturation": [
        "20260101T000010Z-cpu-saturation-a00010",
        "20260101T000011Z-cpu-saturation-a00011",
    ],
    "memory_leak": [
        "20260101T000012Z-memory-leak-a00012",
        "20260101T000013Z-memory-leak-a00013",
    ],
    "service_failure": [
        "20260101T000014Z-service-failure-a00014",
        "20260101T000015Z-service-failure-a00015",
    ],
    "dependency_failure": [
        "20260101T000016Z-dependency-failure-a00016",
        "20260101T000017Z-dependency-failure-a00017",
    ],
    "high_latency": [
        "20260101T000018Z-high-latency-a00018",
        "20260101T000019Z-high-latency-a00019",
    ],
}
SERVICES = ("ad", "email", "payment", "checkout", "frontend", "image-provider")
TARGETS = {
    "normal": set(),
    "cpu_saturation": {"ad"},
    "memory_leak": {"email"},
    "service_failure": {"payment"},
    "dependency_failure": {"checkout", "payment"},
    "high_latency": {"frontend", "image-provider"},
}


def _service_rows() -> list[dict[str, object]]:
    features = load_catalog()["service_windows"]["feature_columns"]
    rows: list[dict[str, object]] = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for scenario, run_ids in RUNS.items():
        windows = 25 if scenario == "normal" else 6
        for run_index, run_id in enumerate(run_ids):
            for window in range(windows):
                service = SERVICES[window % len(SERVICES)]
                timestamp = start + timedelta(hours=len(rows), minutes=window)
                values = {name: 0.0 for name in features}
                values.update(
                    {
                        "log_count": 10 + (window % 4),
                        "span_count": 20 + (window % 5),
                        "span_duration_ms_mean": 5.0 + (window % 3),
                        "span_duration_ms_p95": 9.0 + (window % 3),
                        "span_duration_ms_p99": 10.0 + (window % 3),
                        "metric_name_count": 1,
                        "metric_point_count": 1,
                        "metric_gauge_count": 1,
                        "telemetry_observation_count": 31 + (window % 5),
                    }
                )
                if service in TARGETS[scenario]:
                    values["span_duration_ms_p95"] = 500.0 + run_index
                    values["log_error_rate"] = 0.9
                rows.append(
                    {
                        "feature_schema_version": 1,
                        "window_id": f"{run_id}-{window}",
                        "run_id": run_id,
                        "service_name": service,
                        "window_start_utc": timestamp,
                        "window_end_utc": timestamp + timedelta(seconds=60),
                        "window_seconds": 60,
                        "source_event_count": 31,
                        "scenario": scenario,
                        "label": scenario,
                        "is_anomaly": scenario != "normal",
                        **values,
                    }
                )
    return rows


def _metric_rows(service_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for index, service_row in enumerate(service_rows):
        scenario = str(service_row["scenario"])
        service = str(service_row["service_name"])
        value = 10.0 + (index % 3) * 0.1
        if service in TARGETS[scenario]:
            value = 100.0
        rows.append(
            {
                "feature_schema_version": 1,
                "metric_window_id": f"metric-{index}",
                "run_id": service_row["run_id"],
                "service_name": service,
                "window_start_utc": service_row["window_start_utc"],
                "window_end_utc": service_row["window_end_utc"],
                "window_seconds": 60,
                "metric_name": "fixture.temperature",
                "unit": "Cel",
                "metric_type": "Gauge",
                "scenario": scenario,
                "label": scenario,
                "is_anomaly": scenario != "normal",
                "metric_point_count": 1,
                "metric_series_count": 1,
                "metric_value_mean": value,
                "metric_value_std": 0.0,
                "metric_value_min": value,
                "metric_value_max": value,
                "metric_value_p50": value,
                "metric_value_p95": value,
                "metric_value_p99": value,
                "metric_value_first": value,
                "metric_value_last": value,
                "histogram_datapoint_count": 0,
                "histogram_observation_count": 0,
                "histogram_sum": None,
                "histogram_mean": None,
                "histogram_min": None,
                "histogram_max": None,
                "summary_datapoint_count": 0,
                "summary_observation_count": 0,
                "summary_sum": None,
                "summary_mean": None,
            }
        )
    return rows


@pytest.fixture
def synthetic_dataset(tmp_path: Path) -> FeatureDataset:
    data_root = tmp_path / "data"
    dataset_id = "phase4-v1-fixture"
    dataset_dir = data_root / "features" / dataset_id
    dataset_dir.mkdir(parents=True)
    service_rows = _service_rows()
    metric_rows = _metric_rows(service_rows)
    pq.write_table(pa.Table.from_pylist(service_rows), dataset_dir / "service_windows.parquet")
    pq.write_table(pa.Table.from_pylist(metric_rows), dataset_dir / "metric_windows.parquet")
    all_runs = [run_id for run_ids in RUNS.values() for run_id in run_ids]
    manifest = {
        "dataset_id": dataset_id,
        "feature_schema_version": 1,
        "source_run_ids": all_runs,
        "source_scenarios": list(RUNS),
        "service_window_rows": len(service_rows),
        "metric_window_rows": len(metric_rows),
    }
    (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for scenario, run_ids in RUNS.items():
        for run_id in run_ids:
            run_dir = data_root / "raw" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "scenario": scenario,
                        "duration_seconds": 60,
                        "validation_status": "PASS",
                        "feature_flag": None if scenario == "normal" else {"restored": True},
                        "expected_affected_services": sorted(TARGETS[scenario]),
                    }
                ),
                encoding="utf-8",
            )
            for filename in ("metrics.jsonl", "logs.jsonl", "traces.jsonl"):
                (run_dir / filename).write_text("{}\n", encoding="utf-8")
    return load_feature_dataset(dataset_dir)
