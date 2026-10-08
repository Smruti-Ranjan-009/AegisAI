from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from aegis_rag_ingestion.contracts import EmbeddingProvider
from aegis_rag_ingestion.embeddings import validate_vectors

from aegis_rag_retrieval.bm25 import BM25Index
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import (
    RankedChunk,
    RetrievalHit,
    SearchFilters,
)
from aegis_rag_retrieval.errors import RetrievalError
from aegis_rag_retrieval.fusion import reciprocal_rank_fusion
from aegis_rag_retrieval.repository import RetrievalRepository

METHODS = frozenset({"bm25", "dense", "hybrid"})


@dataclass(frozen=True)
class BranchResults:
    bm25: tuple[RankedChunk, ...]
    dense: tuple[RankedChunk, ...]
    hybrid: tuple[RetrievalHit, ...]
    timings: dict[str, float]

    def hits(self, method: str, *, limit: int) -> tuple[RetrievalHit, ...]:
        if method == "hybrid":
            return self.hybrid[:limit]
        branch = self.bm25 if method == "bm25" else self.dense
        return tuple(
            RetrievalHit(
                chunk=item.chunk,
                rank=item.rank,
                score=item.score,
                bm25_rank=item.rank if method == "bm25" else None,
                bm25_score=item.score if method == "bm25" else None,
                dense_rank=item.rank if method == "dense" else None,
                dense_score=item.score if method == "dense" else None,
            )
            for item in branch[:limit]
        )


class HybridRetriever:
    def __init__(
        self,
        config: RetrievalConfig,
        repository: RetrievalRepository,
        provider: EmbeddingProvider,
    ) -> None:
        self.config = config
        self.repository = repository
        self.provider = provider
        if provider.dimension != config.embedding_dimension or not provider.normalized:
            raise RetrievalError("embedding provider does not match the stored vector contract")
        self.snapshot = repository.load_active_snapshot()
        if not self.snapshot.chunks:
            raise RetrievalError("active retrieval corpus is empty")
        self.bm25 = BM25Index(
            self.snapshot.chunks,
            k1=config.bm25_k1,
            b=config.bm25_b,
        )

    def retrieve_branches(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
    ) -> BranchResults:
        if not query.strip():
            raise RetrievalError("query must not be blank")
        selected_filters = filters or SearchFilters()
        total_started = perf_counter()

        started = perf_counter()
        bm25 = self.bm25.search(
            query,
            limit=self.config.candidate_k,
            filters=selected_filters,
        )
        bm25_seconds = perf_counter() - started

        started = perf_counter()
        vector = self.provider.embed_query(query)
        validate_vectors([vector], self.config.embedding_dimension, normalized=True)
        embedding_seconds = perf_counter() - started

        started = perf_counter()
        dense = self.repository.dense_search(
            vector,
            limit=self.config.candidate_k,
            filters=selected_filters,
        )
        dense_seconds = perf_counter() - started

        started = perf_counter()
        hybrid = reciprocal_rank_fusion(
            bm25,
            dense,
            rrf_k=self.config.rrf_k,
            limit=self.config.candidate_k,
        )
        fusion_seconds = perf_counter() - started
        return BranchResults(
            bm25=bm25,
            dense=dense,
            hybrid=hybrid,
            timings={
                "bm25_seconds": bm25_seconds,
                "query_embedding_seconds": embedding_seconds,
                "dense_sql_seconds": dense_seconds,
                "rrf_seconds": fusion_seconds,
                "total_seconds": perf_counter() - total_started,
            },
        )

    def search(
        self,
        query: str,
        *,
        method: str = "hybrid",
        top_k: int = 5,
        filters: SearchFilters | None = None,
        include_content: bool = False,
    ) -> dict[str, object]:
        if method not in METHODS:
            raise RetrievalError(f"unsupported retrieval method: {method}")
        if top_k <= 0 or top_k > self.config.candidate_k:
            raise RetrievalError(
                f"top_k must be between 1 and candidate_k ({self.config.candidate_k})"
            )
        selected_filters = filters or SearchFilters()
        started = perf_counter()
        if not query.strip():
            raise RetrievalError("query must not be blank")
        if method == "bm25":
            branch_started = perf_counter()
            ranked = self.bm25.search(
                query,
                limit=self.config.candidate_k,
                filters=selected_filters,
            )
            branch_seconds = perf_counter() - branch_started
            hits = tuple(
                RetrievalHit(
                    chunk=item.chunk,
                    rank=item.rank,
                    score=item.score,
                    bm25_rank=item.rank,
                    bm25_score=item.score,
                )
                for item in ranked[:top_k]
            )
            timings = {
                "bm25_seconds": branch_seconds,
                "total_seconds": perf_counter() - started,
            }
        elif method == "dense":
            embedding_started = perf_counter()
            vector = self.provider.embed_query(query)
            validate_vectors([vector], self.config.embedding_dimension, normalized=True)
            embedding_seconds = perf_counter() - embedding_started
            sql_started = perf_counter()
            ranked = self.repository.dense_search(
                vector,
                limit=self.config.candidate_k,
                filters=selected_filters,
            )
            sql_seconds = perf_counter() - sql_started
            hits = tuple(
                RetrievalHit(
                    chunk=item.chunk,
                    rank=item.rank,
                    score=item.score,
                    dense_rank=item.rank,
                    dense_score=item.score,
                )
                for item in ranked[:top_k]
            )
            timings = {
                "query_embedding_seconds": embedding_seconds,
                "dense_sql_seconds": sql_seconds,
                "total_seconds": perf_counter() - started,
            }
        else:
            branches = self.retrieve_branches(query, filters=selected_filters)
            hits = branches.hits(method, limit=top_k)
            timings = branches.timings
        return {
            "query": query,
            "method": method,
            "top_k": top_k,
            "filters": selected_filters.to_dict(),
            "corpus_fingerprint": self.snapshot.fingerprint,
            "active_documents": self.snapshot.active_documents,
            "active_chunks": len(self.snapshot.chunks),
            "bm25_index_build_seconds": self.bm25.build_seconds,
            "timings": timings,
            "results": [
                hit.to_dict(include_content=include_content)
                for hit in hits
            ],
        }

    def assert_snapshot_unchanged(self) -> None:
        current = self.repository.current_fingerprint()
        if current != self.snapshot.fingerprint:
            raise RetrievalError(
                "active corpus changed during retrieval: "
                f"{self.snapshot.fingerprint} -> {current}"
            )
