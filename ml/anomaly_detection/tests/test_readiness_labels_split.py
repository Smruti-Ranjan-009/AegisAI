from __future__ import annotations

import json

import pytest
from conftest import RUNS

from aegis_anomaly.config import ReadinessRequirements
from aegis_anomaly.errors import AnomalyError
from aegis_anomaly.labels import load_ground_truth
from aegis_anomaly.readiness import check_readiness
from aegis_anomaly.split import RunSplit, build_run_split


def test_readiness_passes_minimum_campaign(synthetic_dataset) -> None:
    result = check_readiness(synthetic_dataset)
    assert result["status"] == "PASS"
    assert result["total_runs"] == 16
    assert result["normal_service_window_count"] == 150


def test_readiness_reports_run_and_window_shortfalls(synthetic_dataset) -> None:
    result = check_readiness(
        synthetic_dataset,
        requirements=ReadinessRequirements(7, 3, 151),
    )
    assert result["status"] == "FAIL"
    assert len(result["errors"]) == 7


def test_readiness_rejects_mixed_capture_duration(synthetic_dataset) -> None:
    run_id = RUNS["normal"][0]
    path = synthetic_dataset.path.parent.parent / "raw" / run_id / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["duration_seconds"] = 30
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = check_readiness(synthetic_dataset)
    assert any("incompatible durations" in error for error in result["errors"])


def test_readiness_rejects_unrestored_fault(synthetic_dataset) -> None:
    run_id = RUNS["cpu_saturation"][0]
    path = synthetic_dataset.path.parent.parent / "raw" / run_id / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["feature_flag"]["restored"] = False
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = check_readiness(synthetic_dataset)
    assert any("not recorded as restored" in error for error in result["errors"])


def test_ground_truth_distinguishes_run_and_service_labels() -> None:
    truth = load_ground_truth()
    target = truth.annotate(
        {"scenario": "dependency_failure", "service_name": "checkout"}
    )
    propagated = truth.annotate(
        {"scenario": "dependency_failure", "service_name": "frontend"}
    )
    normal = truth.annotate({"scenario": "normal", "service_name": "checkout"})
    assert target["run_has_fault"] and target["is_injected_fault_service"]
    assert propagated["run_has_fault"] and not propagated["is_injected_fault_service"]
    assert propagated["ground_truth_role"] == "propagation_ambiguous"
    assert normal["ground_truth_role"] == "normal_negative"


def test_split_has_zero_overlap_and_normal_only_training() -> None:
    scenarios = {run_id: scenario for scenario, ids in RUNS.items() for run_id in ids}
    split = build_run_split(scenarios)
    assert set(split.training_run_ids).isdisjoint(split.validation_run_ids)
    assert set(split.training_run_ids).isdisjoint(split.test_run_ids)
    assert all(scenarios[run_id] == "normal" for run_id in split.training_run_ids)
    assert split == build_run_split(scenarios)


def test_split_validation_rejects_overlap() -> None:
    scenarios = {run_id: scenario for scenario, ids in RUNS.items() for run_id in ids}
    split = build_run_split(scenarios)
    invalid = RunSplit(
        split.training_run_ids,
        split.validation_run_ids + (split.training_run_ids[0],),
        split.test_run_ids,
    )
    with pytest.raises(AnomalyError, match="overlap"):
        invalid.validate(scenarios)
