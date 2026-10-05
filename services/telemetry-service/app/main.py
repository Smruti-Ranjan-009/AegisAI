from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="AegisAI Telemetry Service",
    description="Phase 2 health API; Kafka processing runs in a separate worker process.",
    version="0.2.0",
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="telemetry-service", status="UP")
