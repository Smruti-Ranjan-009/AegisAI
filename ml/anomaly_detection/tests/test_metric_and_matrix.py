from __future__ import annotations

import numpy as np
import pytest

from aegis_anomaly.config import FORBIDDEN_FEATURE_NAMES
from aegis_anomaly.errors import AnomalyError
from aegis_anomaly.feature_matrix import assert_safe_feature_names, build_model_matrix
from aegis_anomaly.labels import load_ground_truth
from aegis_anomaly.metric_baseline import MetricBaselineTransformer
from aegis_anomaly.preprocessing import MedianImputer
from aegis_anomaly.split import build_run_split


def _fitted_transformer(synthetic_dataset):
    service_rows = synthetic_dataset.service_windows.to_pylist()
    metric_rows = synthetic_dataset.metric_windows.to_pylist()
    scenarios = {row["run_id"]: row["scenario"] for row in service_rows}
    split = build_run_split(scenarios)
    services = {row["service_name"] for row in service_rows}
    transformer = MetricBaselineTransformer().fit(
        metric_rows, service_rows, set(split.training_run_ids), services
    )
    return transformer, split, services


def test_metric_baseline_fits_normal_training_only(synthetic_dataset) -> None:
    transformer, split, _ = _fitted_transformer(synthetic_dataset)
    assert transformer.fit_run_ids == tuple(sorted(split.training_run_ids))
    medians_before = dict(transformer.service_baselines)
    transformer.transform(
        synthetic_dataset.metric_windows.to_pylist(),
        synthetic_dataset.service_windows.to_pylist(),
    )
    assert transformer.service_baselines == medians_before


def test_metric_baseline_rejects_fault_training(synthetic_dataset) -> None:
    service_rows = synthetic_dataset.service_windows.to_pylist()
    metric_rows = synthetic_dataset.metric_windows.to_pylist()
    fault_run = next(row["run_id"] for row in service_rows if row["scenario"] != "normal")
    with pytest.raises(AnomalyError, match="fault"):
        MetricBaselineTransformer().fit(
            metric_rows,
            service_rows,
            {fault_run},
            {row["service_name"] for row in service_rows},
        )


def test_sum_values_are_excluded_and_unknown_metrics_are_counted(synthetic_dataset) -> None:
    transformer, split, services = _fitted_transformer(synthetic_dataset)
    row = dict(synthetic_dataset.metric_windows.to_pylist()[0])
    row.update(
        {
            "run_id": split.validation_run_ids[0],
            "metric_name": "unseen.counter",
            "metric_type": "Sum",
            "metric_value_mean": 999999.0,
        }
    )
    service_row = next(
        row
        for row in synthetic_dataset.service_windows.to_pylist()
        if row["run_id"] == split.validation_run_ids[0] and row["service_name"] in services
    )
    row["service_name"] = service_row["service_name"]
    row["window_start_utc"] = service_row["window_start_utc"]
    transformed = transformer.transform([row], [service_row])
    values = next(iter(transformed.values()))
    assert values["metric_baseline_count"] == 0
    assert values["metric_missing_baseline_count"] == 0


def test_unknown_gauge_is_missing_not_fitted(synthetic_dataset) -> None:
    transformer, split, services = _fitted_transformer(synthetic_dataset)
    row = dict(synthetic_dataset.metric_windows.to_pylist()[0])
    service_row = next(
        item
        for item in synthetic_dataset.service_windows.to_pylist()
        if item["run_id"] == split.validation_run_ids[0] and item["service_name"] in services
    )
    row.update(
        {
            "run_id": service_row["run_id"],
            "service_name": service_row["service_name"],
            "window_start_utc": service_row["window_start_utc"],
            "metric_name": "unseen.gauge",
            "metric_type": "Gauge",
        }
    )
    before = len(transformer.global_baselines)
    values = next(iter(transformer.transform([row], [service_row]).values()))
    assert values["metric_missing_baseline_count"] == 1
    assert values["metric_coverage_ratio"] == 0
    assert len(transformer.global_baselines) == before


def test_model_matrix_uses_catalog_and_excludes_metadata(synthetic_dataset) -> None:
    transformer, split, services = _fitted_transformer(synthetic_dataset)
    matrix = build_model_matrix(
        synthetic_dataset,
        set(split.training_run_ids),
        services,
        transformer,
        load_ground_truth(),
    )
    assert matrix.values.shape[1] == len(matrix.feature_names)
    assert not (set(matrix.feature_names) & FORBIDDEN_FEATURE_NAMES)
    assert "metric_coverage_ratio" in matrix.feature_names


def test_metadata_leakage_guard_rejects_forbidden_name() -> None:
    with pytest.raises(AnomalyError, match="Forbidden"):
        assert_safe_feature_names(("log_count", "run_id"))


def test_median_imputer_uses_only_fit_values() -> None:
    training = np.asarray([[1.0, np.nan], [3.0, 8.0]])
    validation = np.asarray([[np.nan, 1000.0]])
    imputer = MedianImputer().fit(training)
    assert np.array_equal(imputer.statistics_, np.asarray([2.0, 8.0]))
    assert np.array_equal(imputer.transform(validation), np.asarray([[2.0, 1000.0]]))
