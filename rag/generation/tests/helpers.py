from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.contracts import RerankedHit, RerankingRun
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import ChunkRecord, RetrievalHit


def reranked_hit(index: int, content: str | None = None) -> RerankedHit:
    chunk = ChunkRecord(
        chunk_id=f"chunk-{index}",
        document_id=f"doc-{index}",
        document_checksum="a" * 64,
        source_path=f"runbooks/source-{index}.md",
        title=f"Source {index}",
        document_type="runbook",
        services=("platform",),
        incident_types=("general",),
        heading_path=(f"Source {index}", "Triage"),
        content=content or f"Evidence content {index}",
    )
    retrieval = RetrievalHit(
        chunk=chunk,
        rank=index,
        score=1 / (60 + index),
        bm25_rank=index,
        bm25_score=1.0,
        dense_rank=index,
        dense_score=0.5,
    )
    return RerankedHit(retrieval, reranker_score=float(10 - index), reranked_rank=index)


class StubRerankingPipeline:
    def __init__(self, tmp_path: Path, results: tuple[RerankedHit, ...]) -> None:
        self.config = RerankingConfig(
            repository=tmp_path,
            runtime_root=tmp_path / "reranking",
            evaluation_root=tmp_path,
            model_cache=tmp_path / "cache",
        )
        retrieval_config = RetrievalConfig(
            repository=tmp_path,
            database_url="postgresql://unused",
            runtime_root=tmp_path / "retrieval",
            evaluation_root=tmp_path,
        )
        self.retriever = SimpleNamespace(config=retrieval_config)
        self.results = results

    def rerank_query(self, query: str, *, filters=None) -> RerankingRun:
        return RerankingRun(
            query=query,
            corpus_fingerprint="f" * 64,
            candidates=tuple(item.retrieval for item in self.results),
            results=self.results,
            timings={
                "retrieval_total_seconds": 0.01,
                "reranker_seconds": 0.02,
                "total_seconds": 0.03,
            },
        )


def grounded_payload() -> dict:
    return {
        "status": "grounded",
        "summary": "Retry pressure exhausted the available capacity.",
        "suspected_causes": [
            {"cause": "Retries amplified demand.", "evidence": ["E1"]}
        ],
        "recommended_actions": [
            {"action": "Bound retries and verify recovery.", "evidence": ["E1", "E2"]}
        ],
        "citations": [{"evidence_id": "E1"}, {"evidence_id": "E2"}],
    }
