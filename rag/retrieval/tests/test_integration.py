from __future__ import annotations

import os
from pathlib import Path

import pytest
from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.database import connect, require_isolated_test_database
from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider
from aegis_rag_ingestion.ingestion import ingest
from alembic import command
from alembic.config import Config

from aegis_rag_retrieval.benchmark import load_benchmark, validate_qrels
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import SearchFilters
from aegis_rag_retrieval.repository import RetrievalRepository
from aegis_rag_retrieval.retriever import HybridRetriever

TEST_URL = os.getenv("AEGIS_RAG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="AEGIS_RAG_TEST_DATABASE_URL is not set")
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def retriever(tmp_path_factory: pytest.TempPathFactory) -> HybridRetriever:
    assert TEST_URL is not None
    require_isolated_test_database(TEST_URL)
    package_root = ROOT / "rag" / "ingestion"
    alembic = Config(str(package_root / "alembic.ini"))
    alembic.set_main_option("script_location", str(package_root / "migrations"))
    alembic.set_main_option(
        "sqlalchemy.url",
        TEST_URL.replace("postgresql://", "postgresql+psycopg://"),
    )
    command.upgrade(alembic, "head")
    with connect(TEST_URL) as connection:
        connection.execute("TRUNCATE rag.chunks, rag.documents, rag.ingestion_runs")
        connection.commit()
    temp = tmp_path_factory.mktemp("retrieval-integration")
    ingestion = IngestionConfig(
        repository=ROOT,
        corpus_root=ROOT / "rag" / "knowledge",
        runtime_root=temp / "ingestion",
        database_url=TEST_URL,
        embedding_dimension=384,
        target_tokens=400,
        overlap_tokens=60,
    )
    ingest(ingestion, FakeEmbeddingProvider(384))
    config = RetrievalConfig(
        repository=ROOT,
        database_url=TEST_URL,
        runtime_root=temp / "retrieval",
        evaluation_root=ROOT / "rag" / "evaluation",
    )
    connection_context = connect(TEST_URL)
    connection = connection_context.__enter__()
    instance = HybridRetriever(
        config,
        RetrievalRepository(connection),
        FakeEmbeddingProvider(384),
    )
    yield instance
    connection_context.__exit__(None, None, None)


def test_real_pgvector_dense_and_bm25_share_active_filtered_snapshot(
    retriever: HybridRetriever,
) -> None:
    filters = SearchFilters.validated(
        services=["checkout"],
        incident_types=["dependency_failure"],
    )
    branches = retriever.retrieve_branches("payment dependency unreachable", filters=filters)
    assert branches.bm25
    assert branches.dense
    assert branches.hybrid
    for results in (branches.bm25, branches.dense):
        assert all("checkout" in item.chunk.services for item in results)
        assert all("dependency_failure" in item.chunk.incident_types for item in results)


def test_committed_qrels_resolve_to_active_chunks(retriever: HybridRetriever) -> None:
    benchmark = load_benchmark(
        ROOT / "rag" / "evaluation" / "retrieval_queries_v1.jsonl",
        ROOT / "rag" / "evaluation" / "retrieval_qrels_v1.jsonl",
    )
    validate_qrels(benchmark, retriever.snapshot)
    assert len(benchmark.qrels) == 100


def test_exact_dense_query_has_stable_tie_order(retriever: HybridRetriever) -> None:
    first = retriever.search("database connection exhaustion", method="dense", top_k=10)
    second = retriever.search("database connection exhaustion", method="dense", top_k=10)
    assert [item["chunk_id"] for item in first["results"]] == [
        item["chunk_id"] for item in second["results"]
    ]


def test_inactive_documents_are_excluded_and_change_fingerprint(
    retriever: HybridRetriever,
) -> None:
    assert TEST_URL is not None
    source = "runbooks/cpu-saturation.md"
    original = retriever.snapshot.fingerprint
    try:
        with connect(TEST_URL) as connection:
            connection.execute(
                "UPDATE rag.documents SET active = false WHERE source_path = %s",
                (source,),
            )
            connection.commit()
        with connect(TEST_URL) as connection:
            updated = HybridRetriever(
                retriever.config,
                RetrievalRepository(connection),
                FakeEmbeddingProvider(384),
            )
            assert updated.snapshot.fingerprint != original
            assert all(chunk.source_path != source for chunk in updated.snapshot.chunks)
            results = updated.search("CPU throttling", method="dense", top_k=10)
            assert all(item["source_path"] != source for item in results["results"])
    finally:
        with connect(TEST_URL) as connection:
            connection.execute(
                "UPDATE rag.documents SET active = true WHERE source_path = %s",
                (source,),
            )
            connection.commit()
