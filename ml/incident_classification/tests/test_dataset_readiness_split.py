from __future__ import annotations

import json
from collections import Counter

import pyarrow as pa
import pytest

from aegis_classifier.config import CLASS_NAMES, FROZEN_ANOMALY_MODEL_ID
from aegis_classifier.dataset import (
    assert_safe_feature_names,
    load_catalog,
    validate_table,
)
from aegis_classifier.errors import ClassificationError
from aegis_classifier.labels import validate_class_vocabulary
from aegis_classifier.readiness import check_readiness
from aegis_classifier.split import build_frozen_split


def test_authoritative_class_vocabulary_excludes_normal() -> None:
    assert validate_class_vocabulary() == CLASS_NAMES
    assert "normal" not in CLASS_NAMES


def test_catalog_is_compact_and_leakage_safe() -> None:
    names = tuple(load_catalog()["predictive_columns"])
    assert 20 <= len(names) <= 40
    assert_safe_feature_names(names)
    for forbidden in ("scenario", "run_id", "service_name", "expected_service"):
        assert all(forbidden not in name for name in names)


def test_leakage_feature_name_is_rejected() -> None:
    with pytest.raises(ClassificationError, match="Leakage"):
        assert_safe_feature_names(("safe", "service_name_encoded"))


def test_frozen_split_prefers_new_runs_and_has_zero_overlap() -> None:
    run_scenarios = {}
    preferred = set()
    for scenario in CLASS_NAMES:
        for index in range(6):
            run_id = f"{scenario}-{index}"
            run_scenarios[run_id] = scenario
            if index >= 2:
                preferred.add(run_id)
    split = build_frozen_split(run_scenarios, preferred)
    assert not set(split.development_run_ids) & set(split.test_run_ids)
    assert set(split.test_run_ids) <= preferred
    assert Counter(run_scenarios[item] for item in split.test_run_ids) == {
        name: 2 for name in CLASS_NAMES
    }


def test_split_rejects_fewer_than_six_runs() -> None:
    run_scenarios = {
        f"{scenario}-{index}": scenario for scenario in CLASS_NAMES for index in range(5)
    }
    with pytest.raises(ClassificationError, match="requires at least 6"):
        build_frozen_split(run_scenarios)


def test_readiness_passes_complete_valid_fixture(synthetic_dataset_factory) -> None:
    dataset, raw_root, anomaly_root = synthetic_dataset_factory()
    result = check_readiness(
        dataset, raw_root=raw_root, anomaly_artifact_root=anomaly_root
    )
    assert result["status"] == "PASS"
    assert result["class_counts"] == {name: 6 for name in CLASS_NAMES}
    assert result["development_rows"] == 20
    assert result["test_rows"] == 10


def test_readiness_reports_failed_manifest(synthetic_dataset_factory) -> None:
    dataset, raw_root, anomaly_root = synthetic_dataset_factory()
    run_id = dataset.table.column("run_id")[0].as_py()
    path = raw_root / run_id / "manifest.json"
    document = json.loads(path.read_text())
    document["validation_status"] = "FAIL"
    path.write_text(json.dumps(document))
    result = check_readiness(
        dataset, raw_root=raw_root, anomaly_artifact_root=anomaly_root
    )
    assert result["status"] == "FAIL"
    assert any("did not pass" in error for error in result["errors"])


def test_readiness_reports_missing_or_wrong_anomaly_artifact(
    synthetic_dataset_factory, tmp_path
) -> None:
    dataset, raw_root, _ = synthetic_dataset_factory()
    result = check_readiness(
        dataset, raw_root=raw_root, anomaly_artifact_root=tmp_path / "missing"
    )
    assert result["status"] == "FAIL"
    assert any("unavailable" in error for error in result["errors"])


def test_dataset_quality_rejects_duplicate_run_and_missing_class() -> None:
    names = tuple(load_catalog()["predictive_columns"])
    base = {
        "run_id": "duplicate",
        "scenario": CLASS_NAMES[0],
        "upstream_feature_dataset_id": "features",
        "upstream_anomaly_model_id": FROZEN_ANOMALY_MODEL_ID,
        **{name: 1.0 for name in names},
    }
    table = pa.Table.from_pylist([base, base])
    manifest = {"row_count": 2, "feature_names": list(names)}
    result = validate_table(table, manifest, names)
    assert result["status"] == "FAIL"
    assert any("unique" in error for error in result["errors"])
    assert any("five supported" in error for error in result["errors"])
