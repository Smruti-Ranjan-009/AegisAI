from __future__ import annotations

import pgvector.psycopg
import psycopg
from aegis_rag_generation.errors import GenerationValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.providers import _connect_retrieval_database


def request(*, insufficient: bool = False) -> dict:
    signals = [{"name": "force_insufficient", "value": "true"}] if insufficient else []
    return {
        "schema_version": "rag_diagnosis_v1",
        "incident_id": "incident-1",
        "title": "Checkout latency",
        "description": "Checkout requests are slow.",
        "affected_services": ["checkout"],
        "anomaly": {
            "anomaly_score": 0.8,
            "threshold": 0.5,
            "is_anomaly": True,
            "model_id": "fake-anomaly-v1",
        },
        "classification": {
            "predicted_incident_type": "dependency_failure",
            "class_probabilities": {
                "cpu_saturation": 0.05,
                "memory_leak": 0.05,
                "service_failure": 0.05,
                "dependency_failure": 0.8,
                "high_latency": 0.05,
            },
            "model_id": "fake-classifier-v1",
        },
        "signal_summary": signals,
    }


def test_grounded_diagnosis_is_advisory_and_reconstructs_citation() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/diagnose",
            json=request(),
            headers={"X-Correlation-ID": "phase12-rag-grounded"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "grounded"
        assert body["advisory"] is True
        assert body["requires_human_review"] is True
        assert body["citations"][0]["source_path"] == body["evidence"][0]["source_path"]
        query = body["lineage"]["query"]
        assert "unverified machine hint, not ground truth" in query
        assert body["lineage"]["retrieval"]["filters"] == {}
        assert response.headers["X-Correlation-ID"] == "phase12-rag-grounded"


def test_insufficient_evidence_is_not_a_failure() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/diagnose", json=request(insufficient=True))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "insufficient_evidence"
        assert body["requires_human_review"] is True
        assert body["suspected_causes"] == []
        assert body["recommended_actions"] == []
        assert body["citations"] == []


def test_readiness_fails_when_real_dependencies_did_not_load() -> None:
    with TestClient(app) as client:
        app.state.provider = None
        app.state.load_error = "SLM unavailable"
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "RAG_NOT_READY"


def test_real_database_connection_registers_pgvector(monkeypatch) -> None:
    connection = object()
    registered: list[object] = []
    monkeypatch.setattr(psycopg, "connect", lambda database_url: connection)
    monkeypatch.setattr(pgvector.psycopg, "register_vector", registered.append)

    assert _connect_retrieval_database("postgresql://example") is connection
    assert registered == [connection]


def test_generation_validation_failure_has_stable_error_contract() -> None:
    class InvalidGenerationProvider:
        def diagnose(self, request, correlation_id):
            del request, correlation_id
            raise GenerationValidationError(
                "generation_validation_failed: citations must exactly cover claim evidence"
            )

    with TestClient(app) as client:
        app.state.provider = InvalidGenerationProvider()
        response = client.post("/api/v1/diagnose", json=request())

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "RAG_VALIDATION_FAILED"
