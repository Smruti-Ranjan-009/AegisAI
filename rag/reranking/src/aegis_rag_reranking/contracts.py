from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aegis_rag_retrieval.contracts import RetrievalHit


class RerankerProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    @property
    def load_seconds(self) -> float: ...

    def score(self, query: str, passages: list[str]) -> tuple[float, ...]: ...


@dataclass(frozen=True)
class RerankedHit:
    retrieval: RetrievalHit
    reranker_score: float
    reranked_rank: int

    @property
    def chunk(self):
        return self.retrieval.chunk

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        value = self.retrieval.to_dict(include_content=include_content)
        value.update(
            {
                "rrf_rank": self.retrieval.rank,
                "rrf_score": self.retrieval.score,
                "reranker_score": self.reranker_score,
                "reranked_rank": self.reranked_rank,
            }
        )
        return value


@dataclass(frozen=True)
class RerankingRun:
    query: str
    corpus_fingerprint: str
    candidates: tuple[RetrievalHit, ...]
    results: tuple[RerankedHit, ...]
    timings: dict[str, float]
