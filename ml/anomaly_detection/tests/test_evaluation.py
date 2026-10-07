from __future__ import annotations

import numpy as np

from aegis_anomaly.evaluate import (
    binary_metrics,
    evaluate_scores,
    service_level_metrics,
)


def _metadata():
    return (
        {
            "run_id": "normal-1",
            "scenario": "normal",
            "service_name": "ad",
            "run_has_fault": False,
            "is_injected_fault_service": False,
            "ground_truth_role": "normal_negative",
        },
        {
            "run_id": "fault-1",
            "scenario": "cpu_saturation",
            "service_name": "ad",
            "run_has_fault": True,
            "is_injected_fault_service": True,
            "ground_truth_role": "injected_positive",
        },
        {
            "run_id": "fault-1",
            "scenario": "cpu_saturation",
            "service_name": "frontend",
            "run_has_fault": True,
            "is_injected_fault_service": False,
            "ground_truth_role": "propagation_ambiguous",
        },
    )


def test_service_evaluation_excludes_ambiguous_fault_rows() -> None:
    metrics = service_level_metrics(_metadata(), np.asarray([0.1, 0.9, 0.95]), 0.5)
    assert metrics["row_count"] == 2
    assert metrics["ambiguous_rows_excluded"] == 1
    assert metrics["f1"] == 1.0


def test_degenerate_auc_is_reported_as_none() -> None:
    metrics = binary_metrics(np.asarray([False, False]), np.asarray([0.1, 0.2]), 0.5)
    assert metrics["roc_auc"] is None
    assert metrics["pr_auc"] is None


def test_run_and_localization_metrics() -> None:
    result = evaluate_scores(_metadata(), np.asarray([0.1, 0.9, 0.3]), 0.5)
    assert result["run_level"]["fault_runs_detected"] == 1
    assert result["localization"]["hit_at_1"] == 1.0
    assert result["localization"]["hit_at_3"] == 1.0
    assert result["localization"]["mrr"] == 1.0
    assert result["per_scenario"]["cpu_saturation"]["fault_runs_detected_by_target"] == 1
