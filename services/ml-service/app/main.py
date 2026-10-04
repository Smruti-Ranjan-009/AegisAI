from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="AegisAI ML Service",
    description="Phase 0 service foundation.",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="ml-service", status="UP")
