from __future__ import annotations

import pytest

from aegis_classifier.anomaly_adapter import FrozenAnomalyAdapter
from aegis_classifier.errors import ClassificationError


def test_adapter_rejects_wrong_phase5_model_id(tmp_path) -> None:
    with pytest.raises(ClassificationError, match="requires frozen anomaly model"):
        FrozenAnomalyAdapter("anomaly-v1-wrong", tmp_path)


def test_adapter_reports_missing_frozen_artifact(tmp_path) -> None:
    with pytest.raises(ClassificationError, match="Cannot read frozen anomaly artifact"):
        FrozenAnomalyAdapter(artifact_root=tmp_path)
