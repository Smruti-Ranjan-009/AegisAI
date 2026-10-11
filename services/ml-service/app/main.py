from __future__ import annotations

import logging
import math
import os
import uuid
from contextlib import asynccontextmanager
from time import perf_counter

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from .contracts import (
    AnomalyResult,
    ClassificationResult,
    InferenceRequest,
    InferenceResponse,
    WindowScore,
)
from .providers import ModelProvider, load_provider

logger = logging.getLogger("aegis.ml_service")


class HealthResponse(BaseModel):
    service: str
    status: str


@asynccontextmanager
async def lifespan(application: FastAPI):
    provider, error, load_ms = load_provider()
    application.state.provider = provider
    application.state.load_error = error
    application.state.load_ms = load_ms
    yield


app = FastAPI(
    title="AegisAI ML Service",
    description="Versioned frozen-model inference boundary.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="ml-service", status="UP")


def _provider() -> ModelProvider:
    provider = getattr(app.state, "provider", None)
    if provider is None:
        detail = {"code": "MODEL_NOT_READY", "message": app.state.load_error}
        raise HTTPException(503, detail=detail)
    return provider


@app.get("/ready", tags=["health"])
def ready() -> dict[str, object]:
    _provider()
    return {
        "service": "ml-service",
        "status": "READY",
        "model_load_ms": app.state.load_ms,
    }


@app.get("/api/v1/models", tags=["models"])
def models() -> dict[str, object]:
    return _provider().model_info()


@app.post("/api/v1/inference/analyze", response_model=InferenceResponse, tags=["inference"])
def analyze(
    request: InferenceRequest,
    response: Response,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> InferenceResponse:
    correlation_id = x_correlation_id or str(uuid.uuid4())
    response.headers["X-Correlation-ID"] = correlation_id
    provider = _provider()
    started = perf_counter()
    matrix = np.asarray(
        [
            [np.nan if value is None else value for value in window.values]
            for window in request.windows
        ],
        dtype=np.float64,
    )
    anomaly_started = perf_counter()
    scores, threshold = provider.score_anomaly(matrix)
    anomaly_ms = (perf_counter() - anomaly_started) * 1000
    if len(scores) != len(request.windows) or any(
        not math.isfinite(float(value)) for value in scores
    ):
        detail = {
            "code": "ML_INFERENCE_FAILED",
            "message": "anomaly model returned invalid scores",
        }
        raise HTTPException(502, detail=detail)
    window_scores = [
        WindowScore(
            window_id=window.window_id,
            service_name=window.service_name,
            anomaly_score=float(score),
            is_anomaly=bool(score > threshold),
        )
        for window, score in zip(request.windows, scores, strict=True)
    ]
    is_anomaly = any(item.is_anomaly for item in window_scores)
    classification = None
    classification_ms = 0.0
    if is_anomaly:
        classification_started = perf_counter()
        from aegis_classifier.aggregation import aggregate_feature_windows
        from aegis_classifier.anomaly_adapter import ScoredWindow

        transformed = provider.transform(matrix)
        rows = [
            ScoredWindow(
                run_id=request.input_id,
                scenario="online",
                service_name=window.service_name,
                window_id=window.window_id,
                window_start_utc=window.window_start_utc,
                anomaly_score=float(score),
                anomaly_decision=bool(score > threshold),
                features=dict(
                    zip(provider.feature_names, map(float, transformed[index]), strict=True)
                ),
            )
            for index, (window, score) in enumerate(
                zip(request.windows, scores, strict=True)
            )
        ]
        aggregated = aggregate_feature_windows(rows)
        classifier = getattr(provider, "classifier", None)
        names = tuple(classifier.feature_names) if classifier else tuple(aggregated)
        vector = np.asarray([[aggregated[name] for name in names]], dtype=np.float64)
        predicted, probabilities = provider.classify(vector)
        classification = ClassificationResult(
            model=provider.classifier_identity,
            predicted_incident_type=predicted,
            class_probabilities=probabilities,
        )
        classification_ms = (perf_counter() - classification_started) * 1000
    total_ms = (perf_counter() - started) * 1000
    status = "anomaly_detected" if is_anomaly else "no_anomaly_signal"
    logger.info(
        "ml_analysis correlation_id=%s input_id=%s status=%s total_ms=%.3f",
        correlation_id,
        request.input_id,
        status,
        total_ms,
    )
    return InferenceResponse(
        input_id=request.input_id,
        analysis_status=status,
        anomaly=AnomalyResult(
            model=provider.anomaly_identity,
            threshold=float(threshold),
            score=float(max(scores)),
            is_anomaly=is_anomaly,
            windows=window_scores,
        ),
        classification=classification,
        lineage={
            "feature_schema_version": 1,
            "feature_names": list(provider.feature_names),
            "provider": os.getenv("AEGIS_ML_MODEL_SOURCE", "fake"),
        },
        timings_ms={
            "anomaly_inference_ms": anomaly_ms,
            "classification_ms": classification_ms,
            "ml_service_ms": total_ms,
        },
        correlation_id=correlation_id,
    )
