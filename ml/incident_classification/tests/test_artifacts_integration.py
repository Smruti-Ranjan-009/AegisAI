from __future__ import annotations

import numpy as np
import pytest

from aegis_classifier.artifacts import load_bundle
from aegis_classifier.config import CLASS_NAMES, FROZEN_ANOMALY_MODEL_ID
from aegis_classifier.training import matrix_for_runs, train


@pytest.mark.integration
def test_tiny_end_to_end_cv_save_reload_and_score(
    synthetic_dataset_factory, tmp_path
) -> None:
    dataset, raw_root, anomaly_root = synthetic_dataset_factory()
    result = train(
        dataset,
        output_root=tmp_path / "artifacts",
        raw_root=raw_root,
        anomaly_artifact_root=anomaly_root,
    )
    assert result["reload_verified"] is True
    assert result["selected_model"] in {"logistic_regression", "random_forest"}
    model_dir = tmp_path / "artifacts" / result["model_id"]
    bundle = load_bundle(model_dir / "model.joblib")
    values, _, _ = matrix_for_runs(dataset, set(dataset.split.test_run_ids))
    probabilities = bundle.predict_probabilities(values)
    assert probabilities.shape == (10, 5)
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert bundle.feature_names == tuple(dataset.manifest["feature_names"])
    assert bundle.class_names == CLASS_NAMES
    assert bundle.upstream_anomaly_model_id == FROZEN_ANOMALY_MODEL_ID
    assert (model_dir / "test_predictions.parquet").is_file()
    assert (model_dir / "cv_results.json").is_file()
