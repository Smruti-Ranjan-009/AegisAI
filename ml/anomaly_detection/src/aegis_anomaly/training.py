from __future__ import annotations

import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import sklearn

from . import __version__
from .artifacts import (
    AnomalyBundle,
    artifact_root,
    deterministic_model_id,
    load_bundle,
    save_bundle,
    save_json,
)
from .config import MIN_SERVICE_NORMAL_WINDOWS, DetectorConfig
from .data import FeatureDataset
from .errors import AnomalyError
from .evaluate import evaluate_scores
from .feature_matrix import ModelMatrix, build_model_matrix
from .isolation_forest import IsolationForestDetector
from .labels import ScenarioGroundTruth
from .metric_baseline import MetricBaselineTransformer
from .preprocessing import MedianImputer
from .readiness import check_readiness
from .robust_detector import RobustZScoreDetector
from .split import build_run_split
from .threshold import calibrate_threshold


def _run_scenarios(dataset: FeatureDataset) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in dataset.service_windows.select(["run_id", "scenario"]).to_pylist():
        prior = output.setdefault(row["run_id"], row["scenario"])
        if prior != row["scenario"]:
            raise AnomalyError(f"Run {row['run_id']} has conflicting scenarios.")
    return output


def _normal_scores(matrix: ModelMatrix, scores: np.ndarray) -> np.ndarray:
    indices = [index for index, row in enumerate(matrix.metadata) if not row["run_has_fault"]]
    if not indices:
        raise AnomalyError("Validation matrix contains no normal rows for threshold calibration.")
    return scores[indices]


def _selection_key(name: str, evaluation: dict[str, Any], target_fpr: float) -> tuple[float, ...]:
    service = evaluation["service_level"]
    run = evaluation["run_level"]
    localization = evaluation["localization"]
    fpr = service["normal_fpr"] if service["normal_fpr"] is not None else 1.0
    run_recall = run["recall"]
    hit_at_1 = localization["hit_at_1"] or 0.0
    roc_auc = service["roc_auc"] or 0.0
    simplicity = 0.0 if name == "robust_zscore" else 1.0
    return abs(fpr - target_fpr), -run_recall, -hit_at_1, -roc_auc, simplicity


def _prediction_rows(
    split_name: str,
    matrix: ModelMatrix,
    scores: np.ndarray,
    threshold: float,
) -> list[dict[str, Any]]:
    return [
        {
            "split": split_name,
            "window_id": item["window_id"],
            "run_id": item["run_id"],
            "scenario": item["scenario"],
            "service_name": item["service_name"],
            "window_start_utc": item["window_start_utc"],
            "window_end_utc": item["window_end_utc"],
            "run_has_fault": item["run_has_fault"],
            "is_injected_fault_service": item["is_injected_fault_service"],
            "ground_truth_role": item["ground_truth_role"],
            "anomaly_score": float(score),
            "is_anomaly_prediction": bool(score > threshold),
        }
        for item, score in zip(matrix.metadata, scores, strict=True)
    ]


def train(
    dataset: FeatureDataset,
    ground_truth: ScenarioGroundTruth,
    *,
    detector_config: DetectorConfig | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    detector_config = detector_config or DetectorConfig()
    readiness = check_readiness(dataset)
    if readiness["status"] != "PASS":
        raise AnomalyError("Dataset readiness failed: " + "; ".join(readiness["errors"]))
    started = time.perf_counter()
    run_scenarios = _run_scenarios(dataset)
    split = build_run_split(run_scenarios, detector_config.random_state)
    eligible_services = set(readiness["eligible_services"])
    service_rows = dataset.service_windows.to_pylist()
    metric_rows = dataset.metric_windows.to_pylist()

    metric_transformer = MetricBaselineTransformer(MIN_SERVICE_NORMAL_WINDOWS).fit(
        metric_rows,
        service_rows,
        set(split.training_run_ids),
        eligible_services,
    )
    train_matrix = build_model_matrix(
        dataset,
        set(split.training_run_ids),
        eligible_services,
        metric_transformer,
        ground_truth,
    )
    validation_matrix = build_model_matrix(
        dataset,
        set(split.validation_run_ids),
        eligible_services,
        metric_transformer,
        ground_truth,
    )
    if any(item["run_has_fault"] for item in train_matrix.metadata):
        raise AnomalyError("Training matrix contains fault rows.")
    imputer = MedianImputer()
    train_values = imputer.fit_transform(train_matrix.values)
    validation_values = imputer.transform(validation_matrix.values)

    detectors: dict[str, Any] = {
        "robust_zscore": RobustZScoreDetector(detector_config.robust_top_k),
        "isolation_forest": IsolationForestDetector(
            detector_config.isolation_estimators, detector_config.random_state
        ),
    }
    comparisons: dict[str, Any] = {}
    thresholds: dict[str, dict[str, float]] = {}
    validation_scores: dict[str, np.ndarray] = {}
    for name, detector in detectors.items():
        detector.fit(train_values)
        scores = detector.score_samples(validation_values)
        calibration = calibrate_threshold(
            _normal_scores(validation_matrix, scores), detector_config.target_normal_fpr
        )
        evaluation = evaluate_scores(validation_matrix.metadata, scores, calibration["threshold"])
        validation_scores[name] = scores
        thresholds[name] = calibration
        comparisons[name] = {
            "threshold": calibration,
            "validation": evaluation,
            "selection_key": list(
                _selection_key(name, evaluation, detector_config.target_normal_fpr)
            ),
        }
    selected_name = min(
        detectors,
        key=lambda name: _selection_key(
            name, comparisons[name]["validation"], detector_config.target_normal_fpr
        ),
    )
    selected_detector = detectors[selected_name]
    selected_threshold = thresholds[selected_name]["threshold"]

    # The test split is materialized and scored only after selection and threshold are frozen.
    test_matrix = build_model_matrix(
        dataset,
        set(split.test_run_ids),
        eligible_services,
        metric_transformer,
        ground_truth,
    )
    test_values = imputer.transform(test_matrix.values)
    scoring_started = time.perf_counter()
    test_scores = selected_detector.score_samples(test_values)
    scoring_seconds = time.perf_counter() - scoring_started
    test_evaluation = evaluate_scores(test_matrix.metadata, test_scores, selected_threshold)

    identity = {
        "feature_dataset_id": dataset.dataset_id,
        "feature_schema_version": dataset.manifest["feature_schema_version"],
        "split": split.as_dict(),
        "model_type": selected_name,
        "detector_config": detector_config.__dict__,
        "threshold_policy": "normal_validation_quantile",
    }
    model_id = deterministic_model_id(identity)
    model_dir = artifact_root(output_root) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    bundle = AnomalyBundle(
        model_id,
        selected_name,
        dataset.dataset_id,
        train_matrix.feature_names,
        tuple(sorted(eligible_services)),
        metric_transformer,
        imputer,
        selected_detector,
        selected_threshold,
    )
    artifact_size = save_bundle(model_dir / "model.joblib", bundle)
    loaded = load_bundle(model_dir / "model.joblib")
    _, reloaded_scores = loaded.matrix_and_scores(dataset, ground_truth, set(split.test_run_ids))
    reload_verified = bool(np.array_equal(test_scores, reloaded_scores))
    if not reload_verified:
        raise AnomalyError("Reloaded artifact scores do not exactly match pre-save scores.")

    training_seconds = time.perf_counter() - started
    predictions = _prediction_rows(
        "validation", validation_matrix, validation_scores[selected_name], selected_threshold
    ) + _prediction_rows("test", test_matrix, test_scores, selected_threshold)
    pq.write_table(
        pa.Table.from_pylist(predictions),
        model_dir / "evaluation_predictions.parquet",
        compression="zstd",
    )
    metrics = {
        "model_id": model_id,
        "dataset_readiness": readiness,
        "detector_comparison": comparisons,
        "selected_detector": selected_name,
        "selection_rule": (
            "minimum validation normal-FPR distance to 5%, then run recall, Hit@1, "
            "service ROC-AUC, and simpler detector"
        ),
        "validation": comparisons[selected_name]["validation"],
        "test": test_evaluation,
        "performance": {
            "training_duration_seconds": training_seconds,
            "test_scoring_duration_seconds": scoring_seconds,
            "test_rows_per_second": (
                test_matrix.row_count / scoring_seconds if scoring_seconds else None
            ),
            "test_scoring_latency_ms_per_row": (
                scoring_seconds * 1000 / test_matrix.row_count
                if test_matrix.row_count
                else None
            ),
        },
        "limitations": [
            "Portfolio-scale synthetic fault campaign rather than production telemetry.",
            "Injected-service ground truth does not label downstream propagation.",
            "Raw Sum metric values are excluded because counter temporality is unavailable.",
        ],
    }
    manifest = {
        "model_id": model_id,
        "model_type": selected_name,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "feature_dataset_id": dataset.dataset_id,
        "feature_schema_version": dataset.manifest["feature_schema_version"],
        **split.as_dict(),
        "eligible_services": sorted(eligible_services),
        "excluded_services": readiness["excluded_services"],
        "feature_names": list(train_matrix.feature_names),
        "preprocessing": {"imputation": "training median", "scaling": "detector-specific"},
        "metric_baseline": {
            "minimum_service_windows": MIN_SERVICE_NORMAL_WINDOWS,
            "fit_run_ids": list(metric_transformer.fit_run_ids),
            "service_window_counts": metric_transformer.service_window_counts,
            "service_baseline_count": len(metric_transformer.service_baselines),
            "global_baseline_count": len(metric_transformer.global_baselines),
            "sum_policy": "raw Sum values excluded",
            "sum_metric_rows_excluded": sum(
                row["metric_type"] == "Sum" for row in metric_rows
            ),
        },
        "detector_parameters": detector_config.__dict__,
        "threshold_policy": "95th percentile of normal validation scores; score > threshold",
        "threshold_value": selected_threshold,
        "row_counts": {
            "training": train_matrix.row_count,
            "validation": validation_matrix.row_count,
            "test": test_matrix.row_count,
        },
        "libraries": {
            "aegis_anomaly_detection": __version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pyarrow": pa.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "artifact_size_bytes": artifact_size,
        "reload_verified": reload_verified,
    }
    save_json(model_dir / "manifest.json", manifest)
    save_json(model_dir / "metrics.json", metrics)
    save_json(model_dir / "threshold.json", thresholds[selected_name])
    save_json(
        model_dir / "feature_schema.json",
        {"feature_schema_version": 1, "feature_names": list(train_matrix.feature_names)},
    )
    save_json(model_dir / "split.json", split.as_dict())
    save_json(model_dir / "training_report.json", metrics)
    return {
        "model_id": model_id,
        "model_dir": str(model_dir),
        "selected_detector": selected_name,
        "threshold": selected_threshold,
        "reload_verified": reload_verified,
        "manifest": manifest,
        "metrics": metrics,
    }
