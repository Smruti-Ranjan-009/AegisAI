from __future__ import annotations

from aegis_rag_retrieval.contracts import RankedChunk, RetrievalHit


def reciprocal_rank_fusion(
    bm25: tuple[RankedChunk, ...],
    dense: tuple[RankedChunk, ...],
    *,
    rrf_k: int = 60,
    limit: int = 10,
) -> tuple[RetrievalHit, ...]:
    by_id: dict[str, dict[str, RankedChunk]] = {}
    for branch, results in (("bm25", bm25), ("dense", dense)):
        for result in results:
            by_id.setdefault(result.chunk.chunk_id, {})[branch] = result

    fused: list[RetrievalHit] = []
    for branches in by_id.values():
        lexical = branches.get("bm25")
        semantic = branches.get("dense")
        score = sum(
            1.0 / (rrf_k + result.rank)
            for result in (lexical, semantic)
            if result is not None
        )
        chunk = lexical.chunk if lexical is not None else semantic.chunk  # type: ignore[union-attr]
        fused.append(
            RetrievalHit(
                chunk=chunk,
                rank=0,
                score=score,
                bm25_rank=lexical.rank if lexical else None,
                bm25_score=lexical.score if lexical else None,
                dense_rank=semantic.rank if semantic else None,
                dense_score=semantic.score if semantic else None,
            )
        )

    def key(hit: RetrievalHit) -> tuple[float, int, str]:
        best_rank = min(rank for rank in (hit.bm25_rank, hit.dense_rank) if rank is not None)
        return (-hit.score, best_rank, hit.chunk.chunk_id)

    ordered = sorted(fused, key=key)[:limit]
    return tuple(
        RetrievalHit(
            chunk=hit.chunk,
            rank=rank,
            score=hit.score,
            bm25_rank=hit.bm25_rank,
            bm25_score=hit.bm25_score,
            dense_rank=hit.dense_rank,
            dense_score=hit.dense_score,
        )
        for rank, hit in enumerate(ordered, start=1)
    )
