import pytest
from helpers import chunk

from aegis_rag_retrieval.contracts import RankedChunk
from aegis_rag_retrieval.fusion import reciprocal_rank_fusion


def test_rrf_exact_scores_and_branch_ranks() -> None:
    a = chunk("a", "alpha")
    b = chunk("b", "beta")
    c = chunk("c", "gamma")
    fused = reciprocal_rank_fusion(
        (
            RankedChunk(a, 1, 9.0),
            RankedChunk(b, 2, 8.0),
        ),
        (
            RankedChunk(b, 1, 0.9),
            RankedChunk(c, 2, 0.8),
        ),
        rrf_k=60,
        limit=3,
    )
    assert [item.chunk.chunk_id for item in fused] == ["b", "a", "c"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[0].bm25_rank == 2
    assert fused[0].dense_rank == 1


def test_rrf_tie_uses_best_rank_then_chunk_id() -> None:
    a = chunk("a", "alpha")
    b = chunk("b", "beta")
    fused = reciprocal_rank_fusion(
        (RankedChunk(b, 1, 1.0),),
        (RankedChunk(a, 1, 1.0),),
        rrf_k=60,
        limit=2,
    )
    assert [item.chunk.chunk_id for item in fused] == ["a", "b"]

