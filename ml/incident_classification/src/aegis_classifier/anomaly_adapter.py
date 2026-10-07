from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from aegis_anomaly.artifacts import load_bundle
from aegis_anomaly.data import FeatureDataset
from aegis_anomaly.feature_matrix import build_model_matrix
from aegis_anomaly.labels import load_ground_truth

from .config import FROZEN_ANOMALY_MODEL_ID, repository_root
from .errors import ClassificationError


@dataclass(frozen=True)
class ScoredWindow:
    run_id: str
    scenario: str
    service_name: str
    window_id: str
    window_start_utc: Any
    anomaly_score: float
    anomaly_decision: bool
    features: dict[str, float]


class FrozenAnomalyAdapter:
    """The only Phase 6 entry point for trusted Phase 5 artifact loading/scoring."""

    def __init__(
        self,
        model_id: str = FROZEN_ANOMALY_MODEL_ID,
        artifact_root: Path | None = None,
    ) -> None:
        if model_id != FROZEN_ANOMALY_MODEL_ID:
            raise ClassificationError(
                f"Phase 6 requires frozen anomaly model {FROZEN_ANOMALY_MODEL_ID}; "
                f"received {model_id}."
            )
        root = artifact_root or repository_root() / "artifacts" / "anomaly_detection"
        self.model_dir = root / model_id
        try:
            manifest = json.loads((self.model_dir / "manifest.json").read_text(encoding="utf-8"))
            threshold = json.loads(
                (self.model_dir / "threshold.json").read_text(encoding="utf-8")
            )
            schema = json.loads(
                (self.model_dir / "feature_schema.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ClassificationError(f"Cannot read frozen anomaly artifact: {exc}") from exc
        if manifest.get("model_id") != model_id:
            raise ClassificationError("Frozen anomaly manifest model ID does not match.")
        if manifest.get("feature_schema_version") != 1:
            raise ClassificationError("Frozen anomaly feature schema must be version 1.")
        try:
            bundle = load_bundle(self.model_dir / "model.joblib")
        except Exception as exc:  # noqa: BLE001 - normalize the upstream artifact error
            raise ClassificationError(f"Cannot load trusted frozen anomaly bundle: {exc}") from exc
        if bundle.model_id != model_id:
            raise ClassificationError("Frozen anomaly bundle model ID does not match.")
        if tuple(schema.get("feature_names", [])) != bundle.feature_names:
            raise ClassificationError("Frozen anomaly feature ordering is inconsistent.")
        if not np.isclose(float(threshold.get("threshold")), bundle.threshold, rtol=0, atol=0):
            raise ClassificationError("Frozen anomaly threshold sidecar is inconsistent.")
        self.model_id = model_id
        self.bundle = bundle
        self.manifest = manifest
        self.threshold_document = threshold

    @property
    def threshold(self) -> float:
        return float(self.bundle.threshold)

    def score(self, dataset: FeatureDataset) -> list[ScoredWindow]:
        required_service_columns = {
            "run_id",
            "scenario",
            "service_name",
            "window_id",
            "window_start_utc",
        }
        if not required_service_columns.issubset(dataset.service_windows.column_names):
            raise ClassificationError("Phase 4 service-window columns are incomplete.")
        try:
            matrix = build_model_matrix(
                dataset,
                set(dataset.manifest["source_run_ids"]),
                set(self.bundle.eligible_services),
                self.bundle.metric_transformer,
                load_ground_truth(),
            )
            values = self.bundle.imputer.transform(matrix.values)
            scores = self.bundle.detector.score_samples(values)
        except Exception as exc:  # noqa: BLE001 - normalize upstream model/data errors
            raise ClassificationError(f"Frozen anomaly scoring failed: {exc}") from exc
        if matrix.feature_names != self.bundle.feature_names:
            raise ClassificationError("Phase 4 matrix does not match frozen anomaly features.")
        if len(scores) != matrix.row_count or not np.all(np.isfinite(scores)):
            raise ClassificationError("Frozen anomaly model emitted invalid scores.")
        rows: list[ScoredWindow] = []
        for index, (metadata, score) in enumerate(zip(matrix.metadata, scores, strict=True)):
            feature_values = {
                name: float(values[index, position])
                for position, name in enumerate(matrix.feature_names)
            }
            rows.append(
                ScoredWindow(
                    run_id=str(metadata["run_id"]),
                    scenario=str(metadata["scenario"]),
                    service_name=str(metadata["service_name"]),
                    window_id=str(metadata["window_id"]),
                    window_start_utc=metadata["window_start_utc"],
                    anomaly_score=float(score),
                    anomaly_decision=bool(score > self.bundle.threshold),
                    features=feature_values,
                )
            )
        return rows
