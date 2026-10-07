from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.pipeline import Pipeline

from .config import CLASS_NAMES, FROZEN_ANOMALY_MODEL_ID, repository_root
from .errors import ClassificationError
from .evaluate import ordered_probabilities


@dataclass
class ClassifierBundle:
    model_id: str
    model_type: str
    classification_dataset_id: str
    upstream_feature_dataset_id: str
    upstream_anomaly_model_id: str
    feature_names: tuple[str, ...]
    class_names: tuple[str, ...]
    pipeline: Pipeline
    aggregation_configuration: dict[str, Any]

    def predict_probabilities(self, values: np.ndarray) -> np.ndarray:
        if values.ndim != 2 or values.shape[1] != len(self.feature_names):
            raise ClassificationError("Classifier input does not match persisted feature order.")
        return ordered_probabilities(self.pipeline, values, self.class_names)

    def predict(self, values: np.ndarray) -> np.ndarray:
        probabilities = self.predict_probabilities(values)
        return np.asarray([self.class_names[index] for index in np.argmax(probabilities, axis=1)])


def artifact_root(path: Path | None = None) -> Path:
    return path or repository_root() / "artifacts" / "incident_classification"


def deterministic_model_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "classifier-v1-" + hashlib.sha256(encoded).hexdigest()[:12]


def save_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"Cannot load classifier JSON {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ClassificationError(f"Classifier JSON must contain an object: {path}")
    return document


def save_bundle(path: Path, bundle: ClassifierBundle) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path, compress=3)
    return path.stat().st_size


def load_bundle(path: Path) -> ClassifierBundle:
    # Joblib is pickle-based; only trusted locally generated artifacts are supported.
    try:
        bundle = joblib.load(path)
    except Exception as exc:  # noqa: BLE001 - deserializer errors vary
        raise ClassificationError(f"Cannot load trusted classifier artifact: {exc}") from exc
    if not isinstance(bundle, ClassifierBundle):
        raise ClassificationError("Artifact did not contain an AegisAI classifier bundle.")
    if bundle.upstream_anomaly_model_id != FROZEN_ANOMALY_MODEL_ID:
        raise ClassificationError("Classifier bundle references the wrong Phase 5 model.")
    if bundle.class_names != CLASS_NAMES:
        raise ClassificationError("Classifier artifact class ordering is invalid.")
    return bundle


def resolve_model(value: str | Path, root: Path | None = None) -> Path:
    candidate = Path(value)
    path = candidate if candidate.is_dir() else artifact_root(root) / candidate
    if not path.is_dir():
        raise ClassificationError(f"Classifier artifact does not exist: {path}")
    return path.resolve()
