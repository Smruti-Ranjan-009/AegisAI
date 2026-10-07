from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from aegis_classifier.config import CLASS_NAMES, FROZEN_ANOMALY_MODEL_ID
from aegis_classifier.dataset import _schema, load_catalog, load_classification_dataset
from aegis_classifier.split import build_frozen_split


@pytest.fixture
def synthetic_dataset_factory(tmp_path: Path) -> Callable[[], tuple[object, Path, Path]]:
    def build():
        feature_names = tuple(load_catalog()["predictive_columns"])
        rows = []
        new_ids = set()
        run_scenarios = {}
        for class_index, scenario in enumerate(CLASS_NAMES):
            for run_index in range(6):
                run_id = f"2026010{class_index + 1}T00000{run_index}Z-{scenario}-{run_index:06d}"
                run_scenarios[run_id] = scenario
                if run_index >= 2:
                    new_ids.add(run_id)
                values = {
                    name: float(class_index * 10 + run_index * 0.1 + feature_index * 0.001)
                    for feature_index, name in enumerate(feature_names)
                }
                rows.append(
                    {
                        "run_id": run_id,
                        "scenario": scenario,
                        "upstream_feature_dataset_id": "phase4-fixture",
                        "upstream_anomaly_model_id": FROZEN_ANOMALY_MODEL_ID,
                        **values,
                    }
                )
        split = build_frozen_split(run_scenarios, new_ids)
        root = tmp_path / "classification"
        path = root / "classification-v1-fixture"
        path.mkdir(parents=True)
        table = pa.Table.from_pylist(rows, schema=_schema(feature_names))
        pq.write_table(table, path / "incident_runs.parquet")
        manifest = {
            "dataset_id": path.name,
            "feature_schema_version": 1,
            "upstream_feature_dataset_id": "phase4-fixture",
            "upstream_anomaly_model_id": FROZEN_ANOMALY_MODEL_ID,
            "source_run_ids": sorted(run_scenarios),
            "new_campaign_run_ids": sorted(new_ids),
            "scenario_counts": {name: 6 for name in CLASS_NAMES},
            "row_count": 30,
            "feature_names": list(feature_names),
            "class_names": list(CLASS_NAMES),
            "aggregation_configuration": {"top_k": 3},
            "excluded_services": ["__unknown__", "load-generator"],
        }
        quality = {"status": "PASS", "errors": [], "row_count": 30}
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (path / "quality.json").write_text(json.dumps(quality), encoding="utf-8")
        (path / "split.json").write_text(json.dumps(split.as_dict()), encoding="utf-8")

        raw_root = tmp_path / "raw"
        for run_id, scenario in run_scenarios.items():
            run_path = raw_root / run_id
            run_path.mkdir(parents=True)
            raw_manifest = {
                "run_id": run_id,
                "scenario": scenario,
                "duration_seconds": 60,
                "validation_status": "PASS",
                "feature_flag": {"restored": True},
            }
            (run_path / "manifest.json").write_text(
                json.dumps(raw_manifest), encoding="utf-8"
            )
            for signal in ("metrics.jsonl", "logs.jsonl", "traces.jsonl"):
                (run_path / signal).write_text("{}\n", encoding="utf-8")

        anomaly_root = tmp_path / "anomaly"
        anomaly_path = anomaly_root / FROZEN_ANOMALY_MODEL_ID
        anomaly_path.mkdir(parents=True)
        (anomaly_path / "manifest.json").write_text(
            json.dumps({"model_id": FROZEN_ANOMALY_MODEL_ID}), encoding="utf-8"
        )
        return load_classification_dataset(path), raw_root, anomaly_root

    return build


@pytest.fixture
def separable_values() -> tuple[np.ndarray, np.ndarray]:
    values = []
    labels = []
    for class_index, scenario in enumerate(CLASS_NAMES):
        for sample in range(8):
            row = np.zeros(6, dtype=float)
            row[class_index] = 10 + sample * 0.1
            row[-1] = sample
            values.append(row)
            labels.append(scenario)
    return np.asarray(values), np.asarray(labels)
