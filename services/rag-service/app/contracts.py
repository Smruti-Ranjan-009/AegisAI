from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnomalyContext(StrictModel):
    anomaly_score: float
    threshold: float
    is_anomaly: Literal[True]
    model_id: str = Field(min_length=1)


class ClassificationContext(StrictModel):
    predicted_incident_type: Literal[
        "cpu_saturation", "memory_leak", "service_failure",
        "dependency_failure", "high_latency"
    ]
    class_probabilities: dict[str, float]
    model_id: str = Field(min_length=1)


class Signal(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=300)


class DiagnosisRequest(StrictModel):
    schema_version: Literal["rag_diagnosis_v1"]
    incident_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    affected_services: list[str] = Field(min_length=1, max_length=50)
    anomaly: AnomalyContext
    classification: ClassificationContext
    signal_summary: list[Signal] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def probabilities_are_complete(self) -> DiagnosisRequest:
        expected = {
            "cpu_saturation", "memory_leak", "service_failure",
            "dependency_failure", "high_latency",
        }
        if set(self.classification.class_probabilities) != expected:
            raise ValueError("class_probabilities must contain exactly the five frozen classes")
        return self


class EvidenceReference(StrictModel):
    evidence_id: str
    chunk_id: str
    source_path: str
    heading_path: list[str]
    retrieval_rank: int | None = None
    reranked_rank: int


class Cause(StrictModel):
    cause: str
    evidence: list[str]


class Action(StrictModel):
    action: str
    evidence: list[str]


class Citation(StrictModel):
    evidence_id: str
    source_path: str
    heading_path: list[str]


class DiagnosisResponse(StrictModel):
    schema_version: Literal["rag_diagnosis_result_v1"] = "rag_diagnosis_result_v1"
    query_version: Literal["incident_query_v1"] = "incident_query_v1"
    status: Literal["grounded", "insufficient_evidence"]
    advisory: Literal[True] = True
    requires_human_review: Literal[True] = True
    summary: str
    suspected_causes: list[Cause]
    recommended_actions: list[Action]
    citations: list[Citation]
    evidence: list[EvidenceReference]
    lineage: dict[str, object]
    timings_ms: dict[str, float]
    correlation_id: str

