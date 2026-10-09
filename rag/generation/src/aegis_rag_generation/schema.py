from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceId = Annotated[str, Field(pattern=r"^E[1-5]$")]


class GroundedCause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cause: str = Field(min_length=1)
    evidence: list[EvidenceId]


class GroundedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1)
    evidence: list[EvidenceId]


class RawCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: EvidenceId


class RawGroundedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["grounded", "insufficient_evidence"]
    summary: str = Field(min_length=1)
    suspected_causes: list[GroundedCause]
    recommended_actions: list[GroundedAction]
    citations: list[RawCitation]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    source_path: str
    heading_path: list[str]


class GroundedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["grounded", "insufficient_evidence"]
    summary: str
    suspected_causes: list[GroundedCause]
    recommended_actions: list[GroundedAction]
    citations: list[Citation]
