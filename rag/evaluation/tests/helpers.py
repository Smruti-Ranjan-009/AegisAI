from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.generator import GroundedGenerator
from aegis_rag_generation.provider import FakeSLMProvider
from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.contracts import RerankedHit, RerankingRun
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import ChunkRecord, RetrievalHit

FINGERPRINT = "f5a7d43a5ca429013ef4117b52a36ca68e4e4b4f4e1d16a6d13e89867f59443b"


def hit(index: int, *, content: str | None = None) -> RerankedHit:
    chunk = ChunkRecord(
        chunk_id=f"chunk-{index}",
        document_id=f"doc-{index}",
        document_checksum="a" * 64,
        source_path="runbooks/cpu-saturation.md",
        title="CPU Saturation Response",
        document_type="runbook",
        services=("platform",),
        incident_types=("cpu_saturation",),
        heading_path=("CPU Saturation Response", "Mitigation"),
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
    return RerankedHit(retrieval, float(10 - index), index)


class StubPipeline:
    def __init__(self, root: Path) -> None:
        self.config = RerankingConfig(
            repository=root,
            runtime_root=root / "rerank",
            evaluation_root=root,
            model_cache=root / "cache",
        )
        retrieval = RetrievalConfig(
            repository=root,
            database_url="postgresql://unused",
            runtime_root=root / "retrieval",
            evaluation_root=root,
        )
        self.results = tuple(hit(index) for index in range(1, 6))
        self.retriever = SimpleNamespace(
            config=retrieval,
            snapshot=SimpleNamespace(fingerprint=FINGERPRINT),
        )

    def rerank_query(self, query: str) -> RerankingRun:
        return RerankingRun(
            query=query,
            corpus_fingerprint=FINGERPRINT,
            candidates=tuple(item.retrieval for item in self.results),
            results=self.results,
            timings={"retrieval_total_seconds": 0.01, "reranker_seconds": 0.02},
        )


def grounded_payload() -> dict[str, object]:
    return {
        "status": "grounded",
        "summary": "Optional batch work can be reduced while recovery is observed.",
        "suspected_causes": [{"cause": "Batch work consumes capacity.", "evidence": ["E1"]}],
        "recommended_actions": [
            {"action": "Reduce optional batch work.", "evidence": ["E1"]}
        ],
        "citations": [{"evidence_id": "E1"}],
    }


def generator(root: Path, provider: FakeSLMProvider | None = None) -> GroundedGenerator:
    return GroundedGenerator(
        GenerationConfig(repository=root, model_path=root / "model.gguf"),
        StubPipeline(root),
        provider or FakeSLMProvider(grounded_payload()),
    )


def artifact(status: str = "grounded") -> dict[str, object]:
    response = (
        grounded_payload()
        if status == "grounded"
        else {
            "status": "insufficient_evidence",
            "summary": "The evidence does not support this procedure.",
            "suspected_causes": [],
            "recommended_actions": [],
            "citations": [],
        }
    )
    response["citations"] = [
        {
            "evidence_id": item["evidence_id"],
            "source_path": "runbooks/cpu-saturation.md",
            "heading_path": ["CPU Saturation Response", "Mitigation"],
        }
        for item in response["citations"]
    ]
    return {
        "structured_response": response,
        "evidence": [
            {
                "evidence_id": "E1",
                "source_path": "runbooks/cpu-saturation.md",
                "heading_path": ["CPU Saturation Response", "Mitigation"],
                "content": "Reduce optional batch work and validate latency and queue recovery.",
            }
        ],
    }
