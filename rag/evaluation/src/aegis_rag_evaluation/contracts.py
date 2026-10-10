from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Split = Literal["development", "final"]
CaseType = Literal["grounded", "insufficient", "adversarial"]
ExpectedStatus = Literal["grounded", "insufficient_evidence"]
Variant = Literal["canonical", "no-reranker-ablation"]
NLILabel = Literal["contradiction", "entailment", "neutral"]


class QueryCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^e2e-[gia]-\d{3}$")
    case_type: CaseType
    split: Split
    query: str = Field(min_length=20)
    incident_family: str | None = None
    query_style: str | None = None


class RelevantSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    heading_path: list[str] = Field(min_length=2)
    grade: Literal[1, 2]

    @property
    def key(self) -> tuple[str, tuple[str, ...]]:
        return self.source_path, tuple(self.heading_path)


class GoldRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_status: ExpectedStatus
    relevant_sections: list[RelevantSection]
    required_facts: list[str]
    acceptable_actions: list[str]


class AdversarialOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    evaluation_only: Literal[True]
    target_evidence_rank: int = Field(ge=1, le=5)
    sentinel: Literal["AEGIS_FAKE_SECRET_DO_NOT_OUTPUT"]
    overlay: str = Field(min_length=20)


@dataclass(frozen=True)
class NLIPrediction:
    label: NLILabel
    probabilities: dict[str, float]
    input_tokens: int
    truncated: bool


class NLIProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    @property
    def load_seconds(self) -> float: ...

    def predict(self, pairs: list[tuple[str, str]]) -> tuple[NLIPrediction, ...]: ...


@dataclass(frozen=True)
class BenchmarkBundle:
    cases: tuple[QueryCase, ...]
    gold: dict[str, GoldRecord]
    overlays: dict[str, AdversarialOverlay]
    query_hash: str
    gold_hash: str
    overlay_hash: str
    pipeline_hash: str
    evaluator_hash: str
    benchmark_id: str

    def selected(self, split: Split, variant: Variant = "canonical") -> tuple[QueryCase, ...]:
        cases = tuple(case for case in self.cases if case.split == split)
        if variant == "no-reranker-ablation":
            return tuple(case for case in cases if case.case_type == "grounded")
        return cases
