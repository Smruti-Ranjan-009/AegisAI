from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from aegis_anomaly.artifacts import deterministic_model_id, load_bundle
from aegis_anomaly.labels import load_ground_truth
from aegis_anomaly.training import train


def test_model_id_is_deterministic() -> None:
    assert deterministic_model_id({"b": 2, "a": 1}) == deterministic_model_id(
        {"a": 1, "b": 2}
    )


@pytest.mark.integration
def test_tiny_end_to_end_training_and_reload(synthetic_dataset, tmp_path: Path) -> None:
    result = train(
        synthetic_dataset,
        load_ground_truth(),
        output_root=tmp_path / "artifacts",
    )
    model_dir = Path(result["model_dir"])
    expected = {
        "model.joblib",
        "manifest.json",
        "metrics.json",
        "threshold.json",
        "feature_schema.json",
        "split.json",
        "training_report.json",
        "evaluation_predictions.parquet",
    }
    assert expected <= {path.name for path in model_dir.iterdir()}
    assert result["reload_verified"] is True
    bundle = load_bundle(model_dir / "model.joblib")
    matrix, scores = bundle.matrix_and_scores(synthetic_dataset, load_ground_truth())
    assert len(scores) == matrix.row_count
    assert np.all(np.isfinite(scores))
    predictions = pq.read_table(model_dir / "evaluation_predictions.parquet")
    assert predictions.num_rows > 0
    assert set(result["manifest"]["training_run_ids"]).isdisjoint(
        result["manifest"]["validation_run_ids"]
    )
    assert result["manifest"]["metric_baseline"]["fit_run_ids"] == result["manifest"][
        "training_run_ids"
    ]
