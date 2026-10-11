from __future__ import annotations

import os
from time import perf_counter
from typing import Protocol

from .contracts import DiagnosisRequest, DiagnosisResponse
from .query import build_incident_query


def _connect_retrieval_database(database_url: str):
    import psycopg
    from pgvector.psycopg import register_vector

    connection = psycopg.connect(database_url)
    register_vector(connection)
    return connection


class DiagnosisProvider(Protocol):
    def ready(self) -> dict[str, object]: ...
    def diagnose(self, request: DiagnosisRequest, correlation_id: str) -> DiagnosisResponse: ...


class FakeDiagnosisProvider:
    def ready(self) -> dict[str, object]:
        return {"provider": "fake", "dependencies": "deterministic"}

    def diagnose(self, request: DiagnosisRequest, correlation_id: str) -> DiagnosisResponse:
        query = build_incident_query(request)
        if any(signal.name == "force_insufficient" for signal in request.signal_summary):
            return DiagnosisResponse(
                status="insufficient_evidence",
                summary="The available evidence is insufficient for a grounded diagnosis.",
                suspected_causes=[],
                recommended_actions=[],
                citations=[],
                evidence=[],
                lineage={
                    "query": query,
                    "corpus_fingerprint": "fake-corpus-v1",
                    "embedding": {"model_id": "aegis-fake-embedding-v1"},
                    "retrieval": {"method": "hybrid_rrf", "rrf_k": 60, "filters": {}},
                    "reranker": {"model_id": "aegis-fake-reranker-v1", "candidate_k": 10},
                    "prompt_version": "grounded_incident_v1",
                    "slm": {"model_id": "aegis-fake-slm-v1", "retries": 0},
                },
                timings_ms={
                    "retrieval_ms": 1.0,
                    "reranking_ms": 1.0,
                    "generation_ms": 1.0,
                    "rag_service_ms": 3.0,
                },
                correlation_id=correlation_id,
            )
        evidence = {
            "evidence_id": "E1",
            "chunk_id": "fake-chunk-1",
            "source_path": "runbooks/cross-signal-triage.md",
            "heading_path": ["Cross-signal triage", "Validate"],
            "retrieval_rank": 1,
            "reranked_rank": 1,
        }
        citation = {
            "evidence_id": "E1",
            "source_path": evidence["source_path"],
            "heading_path": evidence["heading_path"],
        }
        return DiagnosisResponse(
            status="grounded",
            summary="The retrieved runbook supports targeted validation before intervention.",
            suspected_causes=[
                {"cause": "The observed signals may reflect resource pressure.", "evidence": ["E1"]}
            ],
            recommended_actions=[
                {
                    "action": "Validate the affected service signals and recovery trend.",
                    "evidence": ["E1"],
                }
            ],
            citations=[citation],
            evidence=[evidence],
            lineage={
                "query": query,
                "corpus_fingerprint": "fake-corpus-v1",
                "embedding": {"model_id": "aegis-fake-embedding-v1"},
                "retrieval": {"method": "hybrid_rrf", "rrf_k": 60, "filters": {}},
                "reranker": {"model_id": "aegis-fake-reranker-v1", "candidate_k": 10},
                "prompt_version": "grounded_incident_v1",
                "slm": {"model_id": "aegis-fake-slm-v1", "retries": 0},
            },
            timings_ms={
                "retrieval_ms": 1.0,
                "reranking_ms": 1.0,
                "generation_ms": 1.0,
                "rag_service_ms": 3.0,
            },
            correlation_id=correlation_id,
        )


class RealDiagnosisProvider:
    def __init__(self) -> None:
        from aegis_rag_generation.config import GenerationConfig
        from aegis_rag_generation.generator import GroundedGenerator
        from aegis_rag_generation.llama_cpp import LocalLlamaCppProvider, verify_model_file
        from aegis_rag_ingestion.embeddings import SentenceTransformerProvider
        from aegis_rag_reranking.config import RerankingConfig
        from aegis_rag_reranking.cross_encoder import CrossEncoderProvider
        from aegis_rag_reranking.reranker import RerankingPipeline
        from aegis_rag_retrieval.config import RetrievalConfig
        from aegis_rag_retrieval.repository import RetrievalRepository
        from aegis_rag_retrieval.retriever import HybridRetriever

        retrieval_config = RetrievalConfig.from_environment()
        reranking_config = RerankingConfig.from_environment()
        generation_config = GenerationConfig.from_environment()
        self.connection = _connect_retrieval_database(retrieval_config.database_url)
        embedding = SentenceTransformerProvider(
            retrieval_config.model_id,
            revision=retrieval_config.model_revision,
            device=retrieval_config.embedding_device,
            batch_size=retrieval_config.embedding_batch_size,
            expected_dimension=retrieval_config.embedding_dimension,
            local_files_only=True,
        )
        retriever = HybridRetriever(
            retrieval_config, RetrievalRepository(self.connection), embedding
        )
        reranker_provider = CrossEncoderProvider(reranking_config, local_files_only=True)
        reranking = RerankingPipeline(reranking_config, retriever, reranker_provider)
        slm = LocalLlamaCppProvider(generation_config)
        self.model_file = verify_model_file(generation_config)
        self.generator = GroundedGenerator(generation_config, reranking, slm)

    def ready(self) -> dict[str, object]:
        self.connection.execute("SELECT 1")
        return {
            "provider": "real",
            "corpus_fingerprint": self.generator.reranking.retriever.snapshot.fingerprint,
            "reranker": self.generator.reranking.provider.model_id,
            "slm": self.generator.provider.health(),
        }

    def diagnose(self, request: DiagnosisRequest, correlation_id: str) -> DiagnosisResponse:
        started = perf_counter()
        outcome = self.generator.diagnose(build_incident_query(request))
        evidence = [
            {
                "evidence_id": item.evidence_id,
                "chunk_id": item.chunk_id,
                "source_path": item.source_path,
                "heading_path": list(item.heading_path),
                "retrieval_rank": None,
                "reranked_rank": item.reranked_rank,
            }
            for item in outcome.evidence
        ]
        performance = outcome.performance
        lineage = {**outcome.lineage, "gguf": self.model_file}
        return DiagnosisResponse(
            status=outcome.response.status,
            summary=outcome.response.summary,
            suspected_causes=[item.model_dump() for item in outcome.response.suspected_causes],
            recommended_actions=[
                item.model_dump() for item in outcome.response.recommended_actions
            ],
            citations=[item.model_dump() for item in outcome.response.citations],
            evidence=evidence,
            lineage=lineage,
            timings_ms={
                "retrieval_ms": 1000 * float(performance.get("retrieval_total_seconds", 0)),
                "reranking_ms": 1000 * float(performance.get("reranker_seconds", 0)),
                "generation_ms": 1000 * float(performance.get("generation_seconds", 0)),
                "rag_service_ms": 1000 * (perf_counter() - started),
            },
            correlation_id=correlation_id,
        )


def load_provider() -> tuple[DiagnosisProvider | None, str | None]:
    mode = os.getenv("AEGIS_RAG_PROVIDER", "fake")
    try:
        if mode == "fake":
            return FakeDiagnosisProvider(), None
        if mode == "real":
            return RealDiagnosisProvider(), None
        raise RuntimeError(f"unsupported AEGIS_RAG_PROVIDER: {mode}")
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
