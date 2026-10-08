from pathlib import Path

from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider
from helpers import chunk

from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import (
    CorpusSnapshot,
    RankedChunk,
    SearchFilters,
)
from aegis_rag_retrieval.repository import corpus_fingerprint
from aegis_rag_retrieval.retriever import HybridRetriever


class FakeRepository:
    def __init__(self) -> None:
        self.dense_calls = 0
        self.chunks = (
            chunk(
                "cpu",
                "CPU throttling and hot threads",
                services=("ad",),
                incident_types=("cpu_saturation",),
            ),
            chunk(
                "db",
                "PostgreSQL connection pool exhaustion",
                services=("postgresql",),
                incident_types=("dependency_failure",),
            ),
        )
        self.fingerprint = corpus_fingerprint(self.chunks)

    def load_active_snapshot(self) -> CorpusSnapshot:
        return CorpusSnapshot(self.fingerprint, self.chunks, 2)

    def dense_search(self, vector, *, limit: int, filters: SearchFilters):
        del vector
        self.dense_calls += 1
        eligible = [item for item in reversed(self.chunks) if filters.matches(item)]
        return tuple(
            RankedChunk(item, rank, 1.0 - rank / 10)
            for rank, item in enumerate(eligible[:limit], start=1)
        )

    def current_fingerprint(self) -> str:
        return self.fingerprint


def test_injected_fake_dense_and_shared_filters(tmp_path: Path) -> None:
    config = RetrievalConfig(
        repository=tmp_path,
        database_url="unused",
        runtime_root=tmp_path / "runtime",
        evaluation_root=tmp_path / "evaluation",
        embedding_dimension=8,
    )
    retriever = HybridRetriever(config, FakeRepository(), FakeEmbeddingProvider(8))
    branches = retriever.retrieve_branches(
        "CPU throttling",
        filters=SearchFilters.validated(services=["ad"]),
    )
    assert [item.chunk.chunk_id for item in branches.bm25] == ["cpu"]
    assert [item.chunk.chunk_id for item in branches.dense] == ["cpu"]
    assert [item.chunk.chunk_id for item in branches.hybrid] == ["cpu"]
    retriever.assert_snapshot_unchanged()


def test_bm25_mode_does_not_execute_dense_branch(tmp_path: Path) -> None:
    repository = FakeRepository()
    config = RetrievalConfig(
        repository=tmp_path,
        database_url="unused",
        runtime_root=tmp_path / "runtime",
        evaluation_root=tmp_path / "evaluation",
        embedding_dimension=8,
    )
    retriever = HybridRetriever(config, repository, FakeEmbeddingProvider(8))
    result = retriever.search("CPU throttling", method="bm25", top_k=1)
    assert result["results"][0]["chunk_id"] == "cpu"
    assert repository.dense_calls == 0
    assert set(result["timings"]) == {"bm25_seconds", "total_seconds"}
