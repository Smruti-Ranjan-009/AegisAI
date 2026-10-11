from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.contracts import CLASS_NAMES, FEATURE_NAMES
from app.main import app


def request(score: float) -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "schema_version": "ml_inference_v1",
        "feature_schema_version": 1,
        "input_id": f"input-{score}",
        "feature_names": list(FEATURE_NAMES),
        "windows": [{
            "window_id": "window-1",
            "service_name": "checkout",
            "window_start_utc": start.isoformat(),
            "window_end_utc": (start + timedelta(seconds=60)).isoformat(),
            "values": [score, *([0.0] * 45)],
        }],
    }


def test_anomaly_negative_skips_classifier() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/inference/analyze",
            json=request(0.2),
            headers={"X-Correlation-ID": "phase12-ml-negative"},
        )
        assert response.status_code == 200
        assert response.json()["analysis_status"] == "no_anomaly_signal"
        assert response.json()["classification"] is None
        assert app.state.provider.classifier_calls == 0
        assert response.headers["X-Correlation-ID"] == "phase12-ml-negative"


@pytest.mark.parametrize(
    ("score", "expected"),
    [(5.0, CLASS_NAMES[0]), (1.0, CLASS_NAMES[1]), (2.0, CLASS_NAMES[2]),
     (3.0, CLASS_NAMES[3]), (4.0, CLASS_NAMES[4])],
)
def test_fake_provider_exercises_each_classifier_label(score: float, expected: str) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/inference/analyze", json=request(score))
        assert response.status_code == 200
        body = response.json()
        assert body["analysis_status"] == "anomaly_detected"
        assert body["classification"]["predicted_incident_type"] == expected
        assert set(body["classification"]["class_probabilities"]) == set(CLASS_NAMES)
        assert "confidence" not in response.text


def test_invalid_feature_order_is_rejected() -> None:
    payload = request(1.0)
    payload["feature_names"] = list(reversed(payload["feature_names"]))
    with TestClient(app) as client:
        assert client.post("/api/v1/inference/analyze", json=payload).status_code == 422


def test_readiness_fails_when_provider_did_not_load() -> None:
    with TestClient(app) as client:
        app.state.provider = None
        app.state.load_error = "configured model unavailable"
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "MODEL_NOT_READY"

