from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

from .audit import append_event
from .config import LifecycleConfig
from .errors import LifecycleError
from .experiments import ensure_experiment
from .integrity import hashes_for, load_json_object, require_model_id, require_schema
from .lineage import (
    anomaly_lineage,
    classifier_lineage,
    reject_large_or_raw,
    relative_to_repository,
)
from .models import FrozenAnomalyPyFunc, anomaly_input_example, classifier_input_example
from .registry import (
    ModelSpec,
    ensure_registered_model,
    find_imported_version,
    require_upstream_anomaly,
    spec_for,
)
from .tracking import finite_metrics, safe_log_params, safe_tags
from .verification import verify_version


def _import_paths(repository: Path, spec: ModelSpec, model_id: str) -> tuple[Path, Path]:
    model_dir = repository / spec.relative_artifact_root / model_id
    if not model_dir.is_dir():
        raise LifecycleError("artifact_missing", f"Frozen model directory is missing: {model_dir}")
    return model_dir, model_dir / "model.joblib"


def _log_lineage(repository: Path, paths: Mapping[str, Path]) -> None:
    for destination, source in sorted(paths.items()):
        reject_large_or_raw(source, repository)
        parent = str(Path("lineage") / Path(destination).parent).replace("\\", "/")
        mlflow.log_artifact(str(source), artifact_path=parent)


def _input_document(example: Any) -> dict[str, Any]:
    return {
        "columns": list(example.columns),
        "data": [[float(value) for value in example.iloc[0].tolist()]],
    }


def _set_version_tags(
    client: MlflowClient, spec: ModelSpec, version: str, values: Mapping[str, Any]
) -> None:
    for key, value in safe_tags(values).items():
        client.set_model_version_tag(spec.registered_name, version, key, value)


def _reuse(
    client: MlflowClient,
    config: LifecycleConfig,
    spec: ModelSpec,
    source_model_id: str,
    artifact_hash: str,
) -> dict[str, Any] | None:
    existing = find_imported_version(client, spec, source_model_id, artifact_hash)
    if existing is None:
        return None
    client.set_registered_model_alias(spec.registered_name, "candidate", str(existing.version))
    return {
        "status": "REUSED",
        "model": spec.key,
        "source_model_id": source_model_id,
        "registered_model": spec.registered_name,
        "version": str(existing.version),
        "run_id": existing.run_id,
        "artifact_sha256": artifact_hash,
        "candidate_alias": str(existing.version),
        "duration_seconds": 0.0,
        "tracking_uri": config.tracking_uri,
    }


def _register_and_approve(
    client: MlflowClient,
    config: LifecycleConfig,
    spec: ModelSpec,
    run_id: str,
    model_uri: str,
    version_tags: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    try:
        version = mlflow.register_model(
            model_uri,
            spec.registered_name,
            await_registration_for=300,
            tags=safe_tags(version_tags),
        )
        _set_version_tags(
            client,
            spec,
            str(version.version),
            {**version_tags, "validation_status": "pending", "lifecycle_status": "candidate"},
        )
        verification = verify_version(
            client, config, spec.key, str(version.version), require_approved=False
        )
        client.set_model_version_tag(
            spec.registered_name, str(version.version), "validation_status", "approved"
        )
        client.set_registered_model_alias(spec.registered_name, "candidate", str(version.version))
    except LifecycleError:
        raise
    except Exception as exc:  # noqa: BLE001 - MLflow registry exceptions vary
        raise LifecycleError("registry_failure", str(exc)) from exc
    event = append_event(
        config,
        {
            "action": "candidate",
            "model": spec.key,
            "registered_model": spec.registered_name,
            "version": str(version.version),
            "source_model_id": version_tags["source_model_id"],
            "validation_result": verification["status"],
            "reason": "validated frozen artifact import",
        },
    )
    return {
        "status": "IMPORTED",
        "model": spec.key,
        "source_model_id": version_tags["source_model_id"],
        "registered_model": spec.registered_name,
        "version": str(version.version),
        "run_id": run_id,
        "artifact_sha256": version_tags["artifact_sha256"],
        "candidate_alias": str(version.version),
        "verification": verification,
        "audit_event": event,
        "duration_seconds": time.perf_counter() - started,
        "tracking_uri": config.tracking_uri,
    }


def _anomaly_metrics(document: dict[str, Any]) -> dict[str, float]:
    validation = document["validation"]
    test = document["test"]
    result = {
        "validation_service_roc_auc": validation["service_level"]["roc_auc"],
        "validation_service_pr_auc": validation["service_level"]["pr_auc"],
        "validation_f1": validation["service_level"]["f1"],
        "validation_normal_fpr": validation["service_level"]["normal_fpr"],
        "validation_hit_at_1": validation["localization"]["hit_at_1"],
        "validation_hit_at_3": validation["localization"]["hit_at_3"],
        "validation_mrr": validation["localization"]["mrr"],
        "test_service_roc_auc": test["service_level"]["roc_auc"],
        "test_service_pr_auc": test["service_level"]["pr_auc"],
        "test_precision": test["service_level"]["precision"],
        "test_recall": test["service_level"]["recall"],
        "test_f1": test["service_level"]["f1"],
        "test_normal_fpr": test["service_level"]["normal_fpr"],
        "run_level_roc_auc": test["run_level"]["roc_auc"],
        "run_level_pr_auc": test["run_level"]["pr_auc"],
        "run_level_precision": test["run_level"]["precision"],
        "run_level_recall": test["run_level"]["recall"],
        "run_level_f1": test["run_level"]["f1"],
        "run_level_fpr": test["run_level"]["normal_fpr"],
        "localization_hit_at_1": test["localization"]["hit_at_1"],
        "localization_hit_at_3": test["localization"]["hit_at_3"],
        "localization_mrr": test["localization"]["mrr"],
    }
    return finite_metrics(result)


def _classifier_metrics(document: dict[str, Any]) -> dict[str, float]:
    final = document["final_test"]
    result: dict[str, Any] = {
        "test_accuracy": final["accuracy"],
        "test_balanced_accuracy": final["balanced_accuracy"],
        "test_macro_precision": final["macro_precision"],
        "test_macro_recall": final["macro_recall"],
        "test_macro_f1": final["macro_f1"],
        "test_weighted_f1": final["weighted_f1"],
        "test_top2_accuracy": final["top_2_accuracy"],
        "test_roc_auc_ovr_macro": final["roc_auc_ovr_macro"],
        "test_log_loss": final["log_loss"],
    }
    for model_name, metrics in document["cross_validation"].items():
        for name in (
            "accuracy_mean",
            "balanced_accuracy_mean",
            "macro_f1_mean",
            "macro_f1_std",
            "top_2_accuracy_mean",
        ):
            result[f"cv_{model_name}_{name}"] = metrics[name]
    for class_name, metrics in final["per_class"].items():
        for name in ("precision", "recall", "f1", "support"):
            result[f"test_{class_name}_{name}"] = metrics[name]
    return finite_metrics(result)


def import_anomaly(
    client: MlflowClient, config: LifecycleConfig, model_id: str
) -> dict[str, Any]:
    started = time.perf_counter()
    spec = spec_for("anomaly")
    model_dir, bundle_path = _import_paths(config.repository, spec, model_id)
    manifest = load_json_object(model_dir / "manifest.json")
    metrics_document = load_json_object(model_dir / "metrics.json")
    require_model_id(manifest, model_id)
    require_schema(manifest)
    from aegis_anomaly.artifacts import load_bundle

    bundle = load_bundle(bundle_path)
    if bundle.model_id != model_id or tuple(bundle.feature_names) != tuple(
        manifest["feature_names"]
    ):
        raise LifecycleError("manifest_invalid", "Anomaly bundle and manifest disagree.")
    lineage = anomaly_lineage(config.repository, model_id, manifest["feature_dataset_id"])
    hashes = hashes_for({"model.joblib": bundle_path, **lineage})
    artifact_hash = hashes["model.joblib"]
    ensure_registered_model(client, spec)
    reused = _reuse(client, config, spec, model_id, artifact_hash)
    if reused:
        return reused
    experiment_id = ensure_experiment(client, config, spec.experiment_name)
    example = anomaly_input_example(bundle)
    output_example = FrozenAnomalyPyFunc()
    output_example.bundle = bundle
    output = output_example.predict(None, example)
    params = {
        "model_type": manifest["model_type"],
        "feature_dataset_id": manifest["feature_dataset_id"],
        "feature_schema_version": manifest["feature_schema_version"],
        "training_run_count": len(manifest["training_run_ids"]),
        "validation_run_count": len(manifest["validation_run_ids"]),
        "test_run_count": len(manifest["test_run_ids"]),
        "feature_count": len(manifest["feature_names"]),
        "random_state": manifest["random_state"],
        "threshold": manifest["threshold_value"],
        "threshold_policy": manifest["threshold_policy"],
        "target_normal_fpr": manifest["detector_parameters"]["target_normal_fpr"],
        "n_estimators": bundle.detector.model.get_params()["n_estimators"],
        "max_samples": bundle.detector.model.get_params()["max_samples"],
        "contamination": bundle.detector.model.get_params()["contamination"],
    }
    tags = {
        "project": "AegisAI",
        "phase": "5",
        "task": spec.task,
        "source_phase": "Phase 5",
        "source_model_id": model_id,
        "source_dataset_id": manifest["feature_dataset_id"],
        "source_artifact_path": relative_to_repository(bundle_path, config.repository),
        "source_manifest_sha256": hashes["source/manifest.json"],
        "artifact_sha256": artifact_hash,
        "feature_schema_version": manifest["feature_schema_version"],
        "lifecycle.import_mode": "frozen_artifact_import",
        "imported_at_utc": datetime.now(UTC).isoformat(),
    }
    with mlflow.start_run(
        experiment_id=experiment_id,
        run_name=f"import-{model_id}",
        tags=safe_tags(tags),
    ) as run:
        safe_log_params(params)
        mlflow.log_metrics(_anomaly_metrics(metrics_document))
        _log_lineage(config.repository, lineage)
        mlflow.log_artifact(str(bundle_path), artifact_path="canonical")
        mlflow.log_dict(hashes, "lineage/integrity.json")
        mlflow.log_dict(_input_document(example), "lineage/input_example.json")
        mlflow.log_dict(
            {
                "purpose": "Detect abnormal service telemetry after normal-only training.",
                "source_model_id": model_id,
                "source_dataset_id": manifest["feature_dataset_id"],
                "feature_schema_version": 1,
                "threshold": manifest["threshold_value"],
                "limitations": metrics_document.get("limitations", []),
                "validation_status": "approved",
                "artifact_hashes": hashes,
            },
            "lineage/model_card.json",
        )
        model_info = mlflow.pyfunc.log_model(
            name="model",
            python_model=FrozenAnomalyPyFunc(),
            artifacts={"frozen_bundle": str(bundle_path)},
            code_paths=[
                str(config.repository / "ml" / "anomaly_detection" / "src" / "aegis_anomaly"),
                str(config.repository / "ml" / "model_lifecycle" / "src" / "aegis_lifecycle"),
            ],
            signature=infer_signature(example, output),
            input_example=example,
            metadata={"feature_order": list(bundle.feature_names), "threshold": bundle.threshold},
            pip_requirements=[
                "mlflow==3.17.0",
                "joblib==1.5.3",
                "numpy==2.4.6",
                "pandas==3.0.6",
                "scikit-learn==1.9.0",
            ],
        )
        run_id = run.info.run_id
    return _register_and_approve(
        client, config, spec, run_id, model_info.model_uri, tags, started
    )


def import_classifier(
    client: MlflowClient, config: LifecycleConfig, model_id: str
) -> dict[str, Any]:
    started = time.perf_counter()
    spec = spec_for("classifier")
    model_dir, bundle_path = _import_paths(config.repository, spec, model_id)
    manifest = load_json_object(model_dir / "manifest.json")
    metrics_document = load_json_object(model_dir / "metrics.json")
    require_model_id(manifest, model_id)
    require_schema(manifest)
    require_upstream_anomaly(client, manifest["upstream_anomaly_model_id"])
    from aegis_classifier.artifacts import load_bundle

    bundle = load_bundle(bundle_path)
    if bundle.model_id != model_id or tuple(bundle.feature_names) != tuple(
        manifest["feature_names"]
    ):
        raise LifecycleError("manifest_invalid", "Classifier bundle and manifest disagree.")
    if bundle.upstream_anomaly_model_id != manifest["upstream_anomaly_model_id"]:
        raise LifecycleError("upstream_dependency_missing", "Classifier lineage is inconsistent.")
    lineage = classifier_lineage(
        config.repository,
        model_id,
        manifest["upstream_feature_dataset_id"],
        manifest["classification_dataset_id"],
    )
    hashes = hashes_for({"model.joblib": bundle_path, **lineage})
    artifact_hash = hashes["model.joblib"]
    ensure_registered_model(client, spec)
    reused = _reuse(client, config, spec, model_id, artifact_hash)
    if reused:
        return reused
    experiment_id = ensure_experiment(client, config, spec.experiment_name)
    example = classifier_input_example(bundle)
    prediction = bundle.pipeline.predict(example)
    params = {
        "model_type": manifest["model_type"],
        "classification_dataset_id": manifest["classification_dataset_id"],
        "upstream_feature_dataset_id": manifest["upstream_feature_dataset_id"],
        "upstream_anomaly_model_id": manifest["upstream_anomaly_model_id"],
        "feature_schema_version": manifest["feature_schema_version"],
        "feature_count": len(manifest["feature_names"]),
        "class_count": len(manifest["class_names"]),
        "top_k": bundle.aggregation_configuration["top_k"],
        "development_rows": manifest["development_rows"],
        "test_rows": manifest["test_rows"],
        "random_state": manifest["random_state"],
        **{
            f"rf_{key}": value
            for key, value in bundle.pipeline.named_steps["classifier"].get_params().items()
            if key
            in {
                "n_estimators",
                "max_depth",
                "min_samples_leaf",
                "class_weight",
                "n_jobs",
                "random_state",
            }
        },
    }
    tags = {
        "project": "AegisAI",
        "phase": "6",
        "task": spec.task,
        "source_phase": "Phase 6",
        "source_model_id": model_id,
        "source_dataset_id": manifest["classification_dataset_id"],
        "upstream_feature_dataset_id": manifest["upstream_feature_dataset_id"],
        "upstream_anomaly_model_id": manifest["upstream_anomaly_model_id"],
        "source_artifact_path": relative_to_repository(bundle_path, config.repository),
        "source_manifest_sha256": hashes["source/manifest.json"],
        "artifact_sha256": artifact_hash,
        "feature_schema_version": manifest["feature_schema_version"],
        "lifecycle.import_mode": "frozen_artifact_import",
        "imported_at_utc": datetime.now(UTC).isoformat(),
    }
    with mlflow.start_run(
        experiment_id=experiment_id,
        run_name=f"import-{model_id}",
        tags=safe_tags(tags),
    ) as run:
        safe_log_params(params)
        mlflow.log_metrics(_classifier_metrics(metrics_document))
        _log_lineage(config.repository, lineage)
        mlflow.log_artifact(str(bundle_path), artifact_path="canonical")
        mlflow.log_dict(hashes, "lineage/integrity.json")
        mlflow.log_dict(_input_document(example), "lineage/input_example.json")
        mlflow.log_dict(
            {
                "purpose": "Classify an already abnormal run into five known incident classes.",
                "source_model_id": model_id,
                "source_dataset_id": manifest["classification_dataset_id"],
                "upstream_anomaly_model_id": manifest["upstream_anomaly_model_id"],
                "classes": manifest["class_names"],
                "feature_schema_version": 1,
                "limitations": metrics_document.get("limitations", []),
                "validation_status": "approved",
                "artifact_hashes": hashes,
            },
            "lineage/model_card.json",
        )
        model_info = mlflow.sklearn.log_model(
            sk_model=bundle.pipeline,
            name="model",
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
            signature=infer_signature(example, prediction),
            input_example=example,
            metadata={
                "feature_order": list(bundle.feature_names),
                "class_order": list(bundle.class_names),
            },
            pip_requirements=[
                "mlflow==3.17.0",
                "numpy==2.4.6",
                "pandas==3.0.6",
                "scikit-learn==1.9.0",
            ],
        )
        run_id = run.info.run_id
    return _register_and_approve(
        client, config, spec, run_id, model_info.model_uri, tags, started
    )
