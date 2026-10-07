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
    ClassifierBundle,
    artifact_root,
    deterministic_model_id,
    load_bundle,
    save_bundle,
    save_json,
)
from .config import CLASS_NAMES, FROZEN_ANOMALY_MODEL_ID, TrainingConfig
from .dataset import ClassificationDataset
from .errors import ClassificationError
from .evaluate import classification_metrics, cross_validate_pipeline, ordered_probabilities
from .logistic_model import build_logistic_pipeline
from .random_forest_model import build_random_forest_pipeline
from .readiness import check_readiness


def matrix_for_runs(
    dataset: ClassificationDataset, run_ids: set[str]
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    feature_names = tuple(dataset.manifest["feature_names"])
    rows = sorted(
        (row for row in dataset.table.to_pylist() if row["run_id"] in run_ids),
        key=lambda row: row["run_id"],
    )
    values = np.asarray([[float(row[name]) for name in feature_names] for row in rows])
    labels = np.asarray([str(row["scenario"]) for row in rows])
    identifiers = [str(row["run_id"]) for row in rows]
    if len(rows) != len(run_ids) or not np.all(np.isfinite(values)):
        raise ClassificationError("Classification matrix is incomplete or non-finite.")
    return values, labels, identifiers


def _select_model(results: dict[str, dict[str, Any]], tolerance: float) -> str:
    logistic = results["logistic_regression"]
    forest = results["random_forest"]
    difference = logistic["macro_f1_mean"] - forest["macro_f1_mean"]
    if abs(difference) > tolerance:
        return "logistic_regression" if difference > 0 else "random_forest"
    balanced_difference = (
        logistic["balanced_accuracy_mean"] - forest["balanced_accuracy_mean"]
    )
    if not np.isclose(balanced_difference, 0.0):
        return "logistic_regression" if balanced_difference > 0 else "random_forest"
    variance_difference = logistic["macro_f1_std"] - forest["macro_f1_std"]
    if not np.isclose(variance_difference, 0.0):
        return "logistic_regression" if variance_difference < 0 else "random_forest"
    return "logistic_regression"


def _explainability(
    model_type: str, pipeline: Any, feature_names: tuple[str, ...]
) -> dict[str, Any]:
    classifier = pipeline.named_steps["classifier"]
    if model_type == "logistic_regression":
        classes = tuple(str(value) for value in classifier.classes_)
        output: dict[str, Any] = {"type": "standardized_coefficients", "classes": {}}
        for class_name in CLASS_NAMES:
            coefficients = classifier.coef_[classes.index(class_name)]
            positive = np.argsort(coefficients)[::-1][:5]
            negative = np.argsort(coefficients)[:5]
            output["classes"][class_name] = {
                "positive": [
                    {"feature": feature_names[index], "coefficient": float(coefficients[index])}
                    for index in positive
                ],
                "negative": [
                    {"feature": feature_names[index], "coefficient": float(coefficients[index])}
                    for index in negative
                ],
            }
        return output
    importances = np.asarray(classifier.feature_importances_)
    indices = np.argsort(importances)[::-1]
    return {
        "type": "impurity_feature_importance",
        "features": [
            {"feature": feature_names[index], "importance": float(importances[index])}
            for index in indices
        ],
    }


def train(
    dataset: ClassificationDataset,
    *,
    output_root: Path | None = None,
    raw_root: Path | None = None,
    anomaly_artifact_root: Path | None = None,
    config: TrainingConfig | None = None,
) -> dict[str, Any]:
    config = config or TrainingConfig()
    readiness = check_readiness(
        dataset, raw_root=raw_root, anomaly_artifact_root=anomaly_artifact_root
    )
    if readiness["status"] != "PASS":
        raise ClassificationError("Dataset readiness failed: " + "; ".join(readiness["errors"]))
    feature_names = tuple(dataset.manifest["feature_names"])
    development_values, development_labels, development_ids = matrix_for_runs(
        dataset, set(dataset.split.development_run_ids)
    )
    test_values, test_labels, test_ids = matrix_for_runs(
        dataset, set(dataset.split.test_run_ids)
    )
    if set(development_ids) & set(test_ids):
        raise ClassificationError("Final test runs entered development data.")

    candidates = {
        "logistic_regression": build_logistic_pipeline(config),
        "random_forest": build_random_forest_pipeline(config),
    }
    cv_started = time.perf_counter()
    cv_results = {
        name: cross_validate_pipeline(
            name, pipeline, development_values, development_labels, config
        )
        for name, pipeline in candidates.items()
    }
    cv_duration = time.perf_counter() - cv_started
    selected_name = _select_model(cv_results, config.practical_tie_tolerance)
    selected_pipeline = candidates[selected_name]
    fit_started = time.perf_counter()
    selected_pipeline.fit(development_values, development_labels)
    fit_duration = time.perf_counter() - fit_started

    # Final test is touched only after CV selection, preprocessing, and model type are frozen.
    scoring_started = time.perf_counter()
    test_probabilities = ordered_probabilities(selected_pipeline, test_values)
    scoring_duration = time.perf_counter() - scoring_started
    test_metrics = classification_metrics(test_labels, test_probabilities)
    predicted = np.asarray(test_metrics.pop("predicted_classes"))

    identity = {
        "classification_dataset_id": dataset.dataset_id,
        "upstream_anomaly_model_id": FROZEN_ANOMALY_MODEL_ID,
        "feature_schema_version": dataset.manifest["feature_schema_version"],
        "aggregation": dataset.manifest["aggregation_configuration"],
        "split": dataset.split.as_dict(),
        "model_type": selected_name,
        "model_parameters": config.__dict__,
        "random_state": config.random_state,
    }
    model_id = deterministic_model_id(identity)
    model_dir = artifact_root(output_root) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    bundle = ClassifierBundle(
        model_id=model_id,
        model_type=selected_name,
        classification_dataset_id=dataset.dataset_id,
        upstream_feature_dataset_id=dataset.manifest["upstream_feature_dataset_id"],
        upstream_anomaly_model_id=FROZEN_ANOMALY_MODEL_ID,
        feature_names=feature_names,
        class_names=CLASS_NAMES,
        pipeline=selected_pipeline,
        aggregation_configuration=dataset.manifest["aggregation_configuration"],
    )
    artifact_size = save_bundle(model_dir / "model.joblib", bundle)
    loaded = load_bundle(model_dir / "model.joblib")
    reloaded_probabilities = loaded.predict_probabilities(test_values)
    reloaded_predictions = loaded.predict(test_values)
    reload_verified = bool(
        np.array_equal(test_probabilities, reloaded_probabilities)
        and np.array_equal(predicted, reloaded_predictions)
    )
    if not reload_verified:
        raise ClassificationError("Reloaded classifier outputs do not exactly match.")

    prediction_rows = []
    for index, run_id in enumerate(test_ids):
        ordered = np.argsort(test_probabilities[index])[::-1]
        prediction_rows.append(
            {
                "run_id": run_id,
                "actual_class": str(test_labels[index]),
                "predicted_class": str(predicted[index]),
                "top_probability": float(test_probabilities[index, ordered[0]]),
                "second_probability": float(test_probabilities[index, ordered[1]]),
                **{
                    f"probability_{class_name}": float(test_probabilities[index, position])
                    for position, class_name in enumerate(CLASS_NAMES)
                },
            }
        )
    pq.write_table(
        pa.Table.from_pylist(prediction_rows),
        model_dir / "test_predictions.parquet",
        compression="zstd",
    )
    explanation = _explainability(selected_name, selected_pipeline, feature_names)
    metrics = {
        "model_id": model_id,
        "dataset_readiness": readiness,
        "selection_rule": (
            "highest mean CV macro F1; within 0.01 use balanced accuracy, lower "
            "macro-F1 standard deviation, then Logistic Regression"
        ),
        "selected_model": selected_name,
        "cross_validation": cv_results,
        "final_test": test_metrics,
        "explainability": explanation,
        "performance": {
            "classification_rows": dataset.table.num_rows,
            "predictive_features": len(feature_names),
            "cross_validation_duration_seconds": cv_duration,
            "final_fit_duration_seconds": fit_duration,
            "test_scoring_duration_seconds": scoring_duration,
            "test_runs_per_second": len(test_ids) / scoring_duration if scoring_duration else None,
        },
        "limitations": [
            "Controlled synthetic fault injection against OpenTelemetry Demo traffic.",
            "Only six independent runs per class and ten final test examples.",
            "Service identity is excluded directly but may be indirectly exposed by telemetry.",
            "Probabilities are not calibrated and no unknown-incident class is trained.",
        ],
    }
    manifest = {
        "model_id": model_id,
        "model_type": selected_name,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "classification_dataset_id": dataset.dataset_id,
        "upstream_feature_dataset_id": dataset.manifest["upstream_feature_dataset_id"],
        "upstream_anomaly_model_id": FROZEN_ANOMALY_MODEL_ID,
        "feature_schema_version": dataset.manifest["feature_schema_version"],
        "feature_names": list(feature_names),
        "class_names": list(CLASS_NAMES),
        **dataset.split.as_dict(),
        "cross_validation_config": {
            "n_splits": config.cv_splits,
            "shuffle": True,
            "random_state": config.random_state,
            "preprocessing": "fold-local sklearn Pipeline",
        },
        "classifier_parameters": config.__dict__,
        "random_seed": config.random_state,
        "development_rows": len(development_ids),
        "test_rows": len(test_ids),
        "cv_metrics": {
            name: {
                "macro_f1_mean": result["macro_f1_mean"],
                "macro_f1_std": result["macro_f1_std"],
                "balanced_accuracy_mean": result["balanced_accuracy_mean"],
                "accuracy_mean": result["accuracy_mean"],
                "top_2_accuracy_mean": result["top_2_accuracy_mean"],
            }
            for name, result in cv_results.items()
        },
        "final_test_metrics": test_metrics,
        "libraries": {
            "aegis_incident_classification": __version__,
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
    save_json(model_dir / "split.json", dataset.split.as_dict())
    save_json(
        model_dir / "feature_schema.json",
        {
            "feature_schema_version": dataset.manifest["feature_schema_version"],
            "feature_names": list(feature_names),
            "class_names": list(CLASS_NAMES),
        },
    )
    save_json(model_dir / "cv_results.json", cv_results)
    save_json(model_dir / "report.json", metrics)
    return {
        "model_id": model_id,
        "model_dir": str(model_dir),
        "selected_model": selected_name,
        "reload_verified": reload_verified,
        "manifest": manifest,
        "metrics": metrics,
    }
