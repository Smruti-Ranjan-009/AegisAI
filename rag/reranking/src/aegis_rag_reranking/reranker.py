from __future__ import annotations

import math
from time import perf_counter

from aegis_rag_retrieval.contracts import RetrievalHit, SearchFilters
from aegis_rag_retrieval.retriever import HybridRetriever

from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.contracts import (
    RerankedHit,
    RerankerProvider,
    RerankingRun,
)
from aegis_rag_reranking.errors import RerankerProviderError, RerankingError
from aegis_rag_reranking.passage import passage_text


def rerank_candidates(
    query: str,
    candidates: tuple[RetrievalHit, ...],
    provider: RerankerProvider,
) -> tuple[RerankedHit, ...]:
    if not query.strip():
        raise RerankingError("query must not be blank")
    if not candidates:
        return ()
    scores = provider.score(query, [passage_text(hit.chunk) for hit in candidates])
    if len(scores) != len(candidates) or any(not math.isfinite(score) for score in scores):
        raise RerankerProviderError("reranker returned an invalid score vector")
    ordered = sorted(
        zip(candidates, scores, strict=True),
        key=lambda item: (-item[1], item[0].rank, item[0].chunk.chunk_id),
    )
    return tuple(
        RerankedHit(hit, float(score), rank)
        for rank, (hit, score) in enumerate(ordered, start=1)
    )


class RerankingPipeline:
    def __init__(
        self,
        config: RerankingConfig,
        retriever: HybridRetriever,
        provider: RerankerProvider,
    ) -> None:
        self.config = config
        self.retriever = retriever
        self.provider = provider

    def rerank_query(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
    ) -> RerankingRun:
        started = perf_counter()
        branches = self.retriever.retrieve_branches(query, filters=filters)
        candidates = branches.hybrid[: self.config.candidate_k]
        rerank_started = perf_counter()
        results = rerank_candidates(query, candidates, self.provider)
        rerank_seconds = perf_counter() - rerank_started
        self.retriever.assert_snapshot_unchanged()
        return RerankingRun(
            query=query,
            corpus_fingerprint=self.retriever.snapshot.fingerprint,
            candidates=candidates,
            results=results,
            timings={
                **{f"retrieval_{key}": value for key, value in branches.timings.items()},
                "reranker_seconds": rerank_seconds,
                "total_seconds": perf_counter() - started,
            },
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: SearchFilters | None = None,
        include_content: bool = False,
    ) -> dict[str, object]:
        if top_k <= 0 or top_k > self.config.candidate_k:
            raise RerankingError(
                f"top_k must be between 1 and candidate_k ({self.config.candidate_k})"
            )
        run = self.rerank_query(query, filters=filters)
        return {
            "query": query,
            "candidate_k": self.config.candidate_k,
            "top_k": top_k,
            "corpus_fingerprint": run.corpus_fingerprint,
            "model_id": self.provider.model_id,
            "model_revision": self.provider.model_revision,
            "model_load_seconds": self.provider.load_seconds,
            "passage_version": self.config.passage_version,
            "timings": run.timings,
            "results": [
                hit.to_dict(include_content=include_content)
                for hit in run.results[:top_k]
            ],
        }
