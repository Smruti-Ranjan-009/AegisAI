from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import FORBIDDEN_FEATURE_NAMES, METRIC_FEATURE_NAMES
from .data import FeatureDataset, load_catalog
from .errors import AnomalyError
from .labels import ScenarioGroundTruth
from .metric_baseline import MetricBaselineTransformer


@dataclass(frozen=True)
class ModelMatrix:
    values: np.ndarray
    feature_names: tuple[str, ...]
    metadata: tuple[dict[str, Any], ...]

    @property
    def row_count(self) -> int:
        return self.values.shape[0]


def assert_safe_feature_names(feature_names: tuple[str, ...]) -> None:
    forbidden = sorted(set(feature_names) & FORBIDDEN_FEATURE_NAMES)
    if forbidden:
        raise AnomalyError(
            "Forbidden metadata/target columns in model matrix: " + ", ".join(forbidden)
        )
    if len(feature_names) != len(set(feature_names)):
        raise AnomalyError("Duplicate model feature names are not allowed.")


def service_feature_names() -> tuple[str, ...]:
    catalog = load_catalog()
    names = tuple(catalog["service_windows"]["feature_columns"])
    assert_safe_feature_names(names)
    return names


def _window_key(row: dict[str, Any]) -> tuple[str, str, Any]:
    return row["run_id"], row["service_name"], row["window_start_utc"]


def build_model_matrix(
    dataset: FeatureDataset,
    run_ids: set[str],
    eligible_services: set[str],
    metric_transformer: MetricBaselineTransformer,
    ground_truth: ScenarioGroundTruth,
) -> ModelMatrix:
    service_rows = [
        row
        for row in dataset.service_windows.to_pylist()
        if row["run_id"] in run_ids and row["service_name"] in eligible_services
    ]
    metric_rows = [
        row
        for row in dataset.metric_windows.to_pylist()
        if row["run_id"] in run_ids and row["service_name"] in eligible_services
    ]
    service_rows.sort(key=lambda row: (row["run_id"], row["window_start_utc"], row["service_name"]))
    deviations = metric_transformer.transform(metric_rows, service_rows)
    base_names = service_feature_names()
    feature_names = base_names + METRIC_FEATURE_NAMES
    assert_safe_feature_names(feature_names)
    values: list[list[float]] = []
    metadata: list[dict[str, Any]] = []
    for row in service_rows:
        metric_features = deviations[_window_key(row)]
        feature_row = [
            np.nan if row[name] is None else float(row[name]) for name in base_names
        ] + [float(metric_features[name]) for name in METRIC_FEATURE_NAMES]
        if any(np.isinf(value) for value in feature_row):
            raise AnomalyError("Model matrix contains an infinite value.")
        values.append(feature_row)
        metadata.append(
            ground_truth.annotate(
                {
                    "window_id": row["window_id"],
                    "run_id": row["run_id"],
                    "scenario": row["scenario"],
                    "service_name": row["service_name"],
                    "window_start_utc": row["window_start_utc"],
                    "window_end_utc": row["window_end_utc"],
                }
            )
        )
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != len(feature_names):
        raise AnomalyError("Model matrix has an unexpected shape.")
    return ModelMatrix(matrix, feature_names, tuple(metadata))
