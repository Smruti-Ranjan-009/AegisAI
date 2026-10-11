from __future__ import annotations

import hashlib
import os
from pathlib import Path
from time import perf_counter
from typing import Protocol

import numpy as np

from .contracts import CLASS_NAMES, FEATURE_NAMES, ModelIdentity


class ModelProvider(Protocol):
    feature_names: tuple[str, ...]
    anomaly_identity: ModelIdentity
    classifier_identity: ModelIdentity

    def model_info(self) -> dict[str, object]: ...
    def transform(self, values: np.ndarray) -> np.ndarray: ...
    def score_anomaly(self, values: np.ndarray) -> tuple[np.ndarray, float]: ...
    def classify(self, features: np.ndarray) -> tuple[str, dict[str, float]]: ...


class FakeModelProvider:
    """Deterministic offline provider used by tests, CI, and default Compose."""

    feature_names = FEATURE_NAMES

    def __init__(self) -> None:
        self.anomaly_calls = 0
        self.classifier_calls = 0
        self.anomaly_identity = ModelIdentity(
            name="AegisAI-AnomalyDetector", model_id="fake-anomaly-v1", source="fake"
        )
        self.classifier_identity = ModelIdentity(
            name="AegisAI-IncidentClassifier", model_id="fake-classifier-v1", source="fake"
        )

    def transform(self, values: np.ndarray) -> np.ndarray:
        return np.nan_to_num(values)

    def score_anomaly(self, values: np.ndarray) -> tuple[np.ndarray, float]:
        self.anomaly_calls += 1
        transformed = self.transform(values)
        return transformed[:, 0], 0.5

    def classify(self, features: np.ndarray) -> tuple[str, dict[str, float]]:
        self.classifier_calls += 1
        index = int(abs(round(float(features[0, 0])))) % len(CLASS_NAMES)
        probabilities = {
            name: (0.8 if position == index else 0.05) for position, name in enumerate(CLASS_NAMES)
        }
        return CLASS_NAMES[index], probabilities

    def model_info(self) -> dict[str, object]:
        return {
            "provider": "fake",
            "loaded": True,
            "anomaly": self.anomaly_identity.model_dump(),
            "classifier": self.classifier_identity.model_dump(),
            "feature_schema_version": 1,
            "feature_names": list(FEATURE_NAMES),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class FrozenArtifactProvider:
    """Trusted-local adapter over the frozen Phase 5 and Phase 6 joblib bundles."""

    def __init__(
        self,
        anomaly_dir: Path,
        classifier_dir: Path,
        *,
        source: str = "frozen_artifact_uri",
        registry_uris: tuple[str, str] | None = None,
    ) -> None:
        from aegis_anomaly.artifacts import load_bundle as load_anomaly
        from aegis_classifier.artifacts import load_bundle as load_classifier

        anomaly_path = anomaly_dir / "model.joblib"
        classifier_path = classifier_dir / "model.joblib"
        self.anomaly = load_anomaly(anomaly_path)
        self.classifier = load_classifier(classifier_path)
        self.feature_names = tuple(self.anomaly.feature_names)
        if self.feature_names != FEATURE_NAMES:
            raise RuntimeError("frozen anomaly feature order differs from ml_inference_v1")
        self.anomaly_identity = ModelIdentity(
            name="AegisAI-AnomalyDetector",
            model_id=self.anomaly.model_id,
            source=source,
            artifact_sha256=_sha256(anomaly_path),
            registry_uri=registry_uris[0] if registry_uris else None,
        )
        self.classifier_identity = ModelIdentity(
            name="AegisAI-IncidentClassifier",
            model_id=self.classifier.model_id,
            source=source,
            artifact_sha256=_sha256(classifier_path),
            registry_uri=registry_uris[1] if registry_uris else None,
        )

    def transform(self, values: np.ndarray) -> np.ndarray:
        return self.anomaly.imputer.transform(values)

    def score_anomaly(self, values: np.ndarray) -> tuple[np.ndarray, float]:
        return self.anomaly.detector.score_samples(self.transform(values)), float(
            self.anomaly.threshold
        )

    def classify(self, features: np.ndarray) -> tuple[str, dict[str, float]]:
        probabilities = self.classifier.predict_probabilities(features)[0]
        mapping = dict(zip(self.classifier.class_names, map(float, probabilities), strict=True))
        return max(mapping, key=mapping.__getitem__), mapping

    def model_info(self) -> dict[str, object]:
        return {
            "provider": self.anomaly_identity.source,
            "loaded": True,
            "anomaly": self.anomaly_identity.model_dump(),
            "classifier": self.classifier_identity.model_dump(),
            "feature_schema_version": 1,
            "feature_names": list(self.feature_names),
        }


def load_provider() -> tuple[ModelProvider | None, str | None, float]:
    started = perf_counter()
    mode = os.getenv("AEGIS_ML_MODEL_SOURCE", "fake")
    try:
        if mode == "fake":
            provider: ModelProvider = FakeModelProvider()
        elif mode == "artifact":
            provider = FrozenArtifactProvider(
                Path(os.environ["AEGIS_ANOMALY_ARTIFACT_URI"]).resolve(),
                Path(os.environ["AEGIS_CLASSIFIER_ARTIFACT_URI"]).resolve(),
            )
        elif mode == "mlflow":
            from aegis_lifecycle.config import LifecycleConfig
            from aegis_lifecycle.registry import resolve_champion
            from aegis_lifecycle.tracking import configure_tracking

            lifecycle_client = configure_tracking(LifecycleConfig.from_environment())
            anomaly = resolve_champion(lifecycle_client, "anomaly")
            classifier = resolve_champion(lifecycle_client, "classifier")
            provider = FrozenArtifactProvider(
                Path(os.environ["AEGIS_ANOMALY_ARTIFACT_URI"]).resolve(),
                Path(os.environ["AEGIS_CLASSIFIER_ARTIFACT_URI"]).resolve(),
                source="mlflow_champion",
                registry_uris=(str(anomaly["model_uri"]), str(classifier["model_uri"])),
            )
        else:
            raise RuntimeError(f"unsupported AEGIS_ML_MODEL_SOURCE: {mode}")
        return provider, None, (perf_counter() - started) * 1000
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}", (perf_counter() - started) * 1000
