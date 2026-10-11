from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from aegis_rag_generation.errors import GenerationValidationError
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from .contracts import DiagnosisRequest, DiagnosisResponse
from .providers import DiagnosisProvider, load_provider

logger = logging.getLogger("aegis.rag_service")


class HealthResponse(BaseModel):
    service: str
    status: str


@asynccontextmanager
async def lifespan(application: FastAPI):
    provider, error = load_provider()
    application.state.provider = provider
    application.state.load_error = error
    yield


app = FastAPI(
    title="AegisAI RAG Service",
    description="Structured grounded incident-diagnosis boundary.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="rag-service", status="UP")


def _provider() -> DiagnosisProvider:
    provider = getattr(app.state, "provider", None)
    if provider is None:
        raise HTTPException(
            503,
            detail={"code": "RAG_NOT_READY", "message": app.state.load_error},
        )
    return provider


@app.get("/ready", tags=["health"])
def ready() -> dict[str, object]:
    try:
        dependencies = _provider().ready()
    except Exception as exc:
        raise HTTPException(
            503,
            detail={"code": "RAG_NOT_READY", "message": str(exc)},
        ) from exc
    return {"service": "rag-service", "status": "READY", **dependencies}


@app.post("/api/v1/diagnose", response_model=DiagnosisResponse, tags=["diagnosis"])
def diagnose(
    request: DiagnosisRequest,
    response: Response,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> DiagnosisResponse:
    correlation_id = x_correlation_id or str(uuid.uuid4())
    response.headers["X-Correlation-ID"] = correlation_id
    try:
        result = _provider().diagnose(request, correlation_id)
    except GenerationValidationError as exc:
        raise HTTPException(
            422,
            detail={"code": "RAG_VALIDATION_FAILED", "message": str(exc)},
        ) from exc
    logger.info(
        "rag_diagnosis correlation_id=%s incident_id=%s status=%s rag_service_ms=%s",
        correlation_id,
        request.incident_id,
        result.status,
        result.timings_ms.get("rag_service_ms"),
    )
    return result
