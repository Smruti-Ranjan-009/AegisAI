from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aegis_rag_generation.schema import GroundedResponse


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    chunk_id: str
    source_path: str
    title: str
    heading_path: tuple[str, ...]
    content: str
    reranked_rank: int

    def prompt_record(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "heading": " > ".join(self.heading_path),
            "source_path": self.source_path,
            "content": self.content,
        }


@dataclass(frozen=True)
class SLMGeneration:
    text: str
    prompt_tokens: int | None
    generated_tokens: int | None
    total_seconds: float
    time_to_first_token_seconds: float | None
    tokens_per_second: float | None


class SLMProvider(Protocol):
    def health(self) -> dict[str, Any]: ...

    def model_info(self) -> dict[str, Any]: ...

    def count_tokens(self, system_prompt: str, user_prompt: str) -> int: ...

    def generate(self, system_prompt: str, user_prompt: str) -> SLMGeneration: ...


@dataclass(frozen=True)
class GenerationOutcome:
    response: GroundedResponse
    evidence: tuple[EvidenceItem, ...]
    evidence_dropped_for_context: tuple[str, ...]
    lineage: dict[str, Any]
    performance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.response.model_dump(),
            "evidence_dropped_for_context": list(self.evidence_dropped_for_context),
            "lineage": self.lineage,
            "performance": self.performance,
        }
