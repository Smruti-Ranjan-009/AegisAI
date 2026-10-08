from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from .errors import LifecycleError
from .experiments import ANOMALY_EXPERIMENT, CLASSIFIER_EXPERIMENT

ModelKey = Literal["anomaly", "classifier"]


@dataclass(frozen=True)
class ModelSpec:
    key: ModelKey
    phase: str
    task: str
    experiment_name: str
    registered_name: str
    default_model_id: str
    relative_artifact_root: str
    required_metrics: tuple[str, ...]
    description: str


SPECS: dict[str, ModelSpec] = {
    "anomaly": ModelSpec(
        key="anomaly",
        phase="5",
        task="anomaly_detection",
        experiment_name=ANOMALY_EXPERIMENT,
        registered_name="AegisAI-AnomalyDetector",
        default_model_id="anomaly-v1-4c84405c580f",
        relative_artifact_root="artifacts/anomaly_detection",
        required_metrics=(
            "test_service_roc_auc",
            "test_service_pr_auc",
            "test_f1",
            "test_normal_fpr",
            "localization_hit_at_1",
            "localization_hit_at_3",
            "localization_mrr",
        ),
        description=(
            "Normal-behavior Isolation Forest anomaly detector built in Phase 5 from "
            "controlled OpenTelemetry Demo captures. It preserves training-only robust "
            "metric baselines, imputation, feature ordering, and strict threshold semantics. "
            "Portfolio-scale only: service F1 is modest, the normal test run was flagged, "
            "and memory-leak localization was weak."
        ),
    ),
    "classifier": ModelSpec(
        key="classifier",
        phase="6",
        task="incident_classification",
        experiment_name=CLASSIFIER_EXPERIMENT,
        registered_name="AegisAI-IncidentClassifier",
        default_model_id="classifier-v1-d37b9861572f",
        relative_artifact_root="artifacts/incident_classification",
        required_metrics=(
            "test_accuracy",
            "test_balanced_accuracy",
            "test_macro_precision",
            "test_macro_recall",
            "test_macro_f1",
            "test_weighted_f1",
            "test_top2_accuracy",
            "test_roc_auc_ovr_macro",
            "test_log_loss",
        ),
        description=(
            "Five-class Phase 6 run-level incident classifier dependent on the frozen Phase 5 "
            "anomaly model. Direct service identity is excluded and top-three anomaly context "
            "is aggregated into 30 features. Portfolio-scale only: test accuracy was 30%, CPU "
            "and high-latency recall were zero, and probabilities are uncalibrated."
        ),
    ),
}


def spec_for(key: str) -> ModelSpec:
    try:
        return SPECS[key]
    except KeyError as exc:
        raise LifecycleError("model_type_invalid", f"Unknown model type: {key}") from exc


def ensure_registered_model(client: MlflowClient, spec: ModelSpec) -> None:
    try:
        client.get_registered_model(spec.registered_name)
    except MlflowException:
        client.create_registered_model(
            spec.registered_name,
            tags={"project": "AegisAI", "task": spec.task, "managed_by": "Phase 7"},
            description=spec.description,
        )
    else:
        client.update_registered_model(spec.registered_name, description=spec.description)


def versions(client: MlflowClient, spec: ModelSpec) -> list[Any]:
    return list(client.search_model_versions(f"name='{spec.registered_name}'"))


def find_imported_version(
    client: MlflowClient, spec: ModelSpec, source_model_id: str, artifact_hash: str
) -> Any | None:
    matching_id = []
    for summary in versions(client, spec):
        version = client.get_model_version(spec.registered_name, summary.version)
        if version.tags.get("source_model_id") == source_model_id:
            matching_id.append(version)
    if not matching_id:
        return None
    for version in matching_id:
        if version.tags.get("artifact_sha256") == artifact_hash:
            return version
    observed = sorted({item.tags.get("artifact_sha256", "missing") for item in matching_id})
    raise LifecycleError(
        "artifact_integrity_mismatch",
        f"Source model {source_model_id} is already registered with different hash(es): "
        f"{', '.join(observed)}.",
    )


def alias_version(client: MlflowClient, spec: ModelSpec, alias: str) -> Any | None:
    try:
        return client.get_model_version_by_alias(spec.registered_name, alias)
    except MlflowException:
        return None


def resolve_champion(client: MlflowClient, key: str) -> dict[str, str]:
    spec = spec_for(key)
    version = alias_version(client, spec, "champion")
    if version is None:
        raise LifecycleError(
            "alias_not_found", f"No champion alias exists for {spec.registered_name}."
        )
    return {
        "model": key,
        "registered_model": spec.registered_name,
        "version": str(version.version),
        "model_uri": f"models:/{spec.registered_name}@champion",
        "source_model_id": version.tags.get("source_model_id", ""),
    }


def require_upstream_anomaly(client: MlflowClient, expected_model_id: str) -> Any:
    spec = spec_for("anomaly")
    champion = alias_version(client, spec, "champion")
    if champion is None:
        raise LifecycleError(
            "upstream_dependency_missing",
            "Classifier registration requires an approved anomaly champion.",
        )
    if champion.tags.get("source_model_id") != expected_model_id:
        raise LifecycleError(
            "upstream_dependency_missing",
            f"Anomaly champion does not resolve expected source model {expected_model_id}.",
        )
    if champion.tags.get("validation_status") != "approved":
        raise LifecycleError(
            "upstream_dependency_missing", "Anomaly champion is not lifecycle-approved."
        )
    return champion
