import pytest
from helpers import hit

from aegis_rag_reranking.errors import RerankerProviderError, RerankingError
from aegis_rag_reranking.passage import passage_text
from aegis_rag_reranking.provider import FakeRerankerProvider
from aegis_rag_reranking.reranker import rerank_candidates


def test_passage_uses_only_semantic_fields() -> None:
    candidate = hit("c1", "Bound retries protect capacity.", rank=1)
    passage = passage_text(candidate.chunk)
    assert passage == (
        "Title: Title c1\nHeading: Title c1 > Triage\n"
        "Content: Bound retries protect capacity."
    )
    assert "general" not in passage
    assert "platform" not in passage


def test_score_order_preserves_all_retrieval_lineage() -> None:
    candidates = (hit("c1", "one", rank=1), hit("c2", "two", rank=2))
    scores = {
        passage_text(candidates[0].chunk): -1.0,
        passage_text(candidates[1].chunk): 2.0,
    }
    results = rerank_candidates("query", candidates, FakeRerankerProvider(scores))
    assert [item.chunk.chunk_id for item in results] == ["c2", "c1"]
    assert results[0].reranked_rank == 1
    assert results[0].retrieval.rank == 2
    value = results[0].to_dict(include_content=True)
    assert value["rrf_rank"] == 2
    assert value["bm25_rank"] == 2
    assert value["dense_rank"] == 3
    assert value["content"] == "two"


def test_equal_scores_use_rrf_rank_then_chunk_id() -> None:
    candidates = (
        hit("z", "same", rank=2),
        hit("b", "same", rank=1),
        hit("a", "same", rank=1),
    )
    provider = FakeRerankerProvider(
        {passage_text(item.chunk): 0.5 for item in candidates}
    )
    results = rerank_candidates("query", candidates, provider)
    assert [item.chunk.chunk_id for item in results] == ["a", "b", "z"]


def test_fake_provider_is_deterministic() -> None:
    provider = FakeRerankerProvider()
    passages = ["one", "two"]
    assert provider.score("query", passages) == provider.score("query", passages)


def test_empty_candidates_return_empty() -> None:
    assert rerank_candidates("query", (), FakeRerankerProvider()) == ()


def test_blank_query_is_rejected() -> None:
    with pytest.raises(RerankingError, match="blank"):
        rerank_candidates(" ", (hit("c1", "one", rank=1),), FakeRerankerProvider())


class BrokenProvider(FakeRerankerProvider):
    def score(self, query: str, passages: list[str]) -> tuple[float, ...]:
        return ()


def test_invalid_provider_vector_fails_closed() -> None:
    with pytest.raises(RerankerProviderError, match="invalid score vector"):
        rerank_candidates("query", (hit("c1", "one", rank=1),), BrokenProvider())
