from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from .config import repository_root
from .data import FeatureDataset
from .errors import AnomalyError
from .feature_matrix import ModelMatrix, build_model_matrix
from .labels import ScenarioGroundTruth
from .metric_baseline import MetricBaselineTransformer
from .preprocessing import MedianImputer


@dataclass
class AnomalyBundle:
    model_id: str
    model_type: str
    feature_dataset_id: str
    feature_names: tuple[str, ...]
    eligible_services: tuple[str, ...]
    metric_transformer: MetricBaselineTransformer
    imputer: MedianImputer
    detector: Any
    threshold: float

    def matrix_and_scores(
        self,
        dataset: FeatureDataset,
        ground_truth: ScenarioGroundTruth,
        run_ids: set[str] | None = None,
    ) -> tuple[ModelMatrix, np.ndarray]:
        selected_runs = run_ids or set(dataset.manifest["source_run_ids"])
        matrix = build_model_matrix(
            dataset,
            selected_runs,
            set(self.eligible_services),
            self.metric_transformer,
            ground_truth,
        )
        if matrix.feature_names != self.feature_names:
            raise AnomalyError("Dataset model feature schema does not match the artifact.")
        values = self.imputer.transform(matrix.values)
        return matrix, self.detector.score_samples(values)


def artifact_root(path: Path | None = None) -> Path:
    return path or repository_root() / "artifacts" / "anomaly_detection"


def deterministic_model_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "anomaly-v1-" + hashlib.sha256(encoded).hexdigest()[:12]


def resolve_model(value: str | Path, root: Path | None = None) -> Path:
    candidate = Path(value)
    path = candidate if candidate.is_dir() else artifact_root(root) / candidate
    if not path.is_dir():
        raise AnomalyError(f"Model artifact does not exist: {path}")
    return path.resolve()


def save_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnomalyError(f"Cannot read artifact JSON {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise AnomalyError(f"Artifact JSON must contain an object: {path}")
    return document


def save_bundle(path: Path, bundle: AnomalyBundle) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path, compress=3)
    return path.stat().st_size


def load_bundle(path: Path) -> AnomalyBundle:
    # Joblib is pickle-based. This function is only for trusted local artifacts.
    try:
        bundle = joblib.load(path)
    except Exception as exc:  # noqa: BLE001 - third-party deserialization errors vary
        raise AnomalyError(f"Cannot load trusted model artifact {path}: {exc}") from exc
    if not isinstance(bundle, AnomalyBundle):
        raise AnomalyError("Artifact did not contain an AegisAI anomaly bundle.")
    return bundle
