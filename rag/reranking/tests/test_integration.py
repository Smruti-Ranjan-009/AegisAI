from __future__ import annotations

import os
from pathlib import Path

import pytest
from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.database import connect, require_isolated_test_database
from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider
from aegis_rag_ingestion.ingestion import ingest
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.repository import RetrievalRepository
from aegis_rag_retrieval.retriever import HybridRetriever
from alembic import command
from alembic.config import Config

from aegis_rag_reranking.benchmark import load_benchmark, validate_qrels
from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.provider import FakeRerankerProvider
from aegis_rag_reranking.reranker import RerankingPipeline

TEST_URL = os.getenv("AEGIS_RAG_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> RerankingPipeline:
    if not TEST_URL:
        pytest.skip("AEGIS_RAG_TEST_DATABASE_URL is not set")
    require_isolated_test_database(TEST_URL)
    package = ROOT / "rag" / "ingestion"
    alembic = Config(str(package / "alembic.ini"))
    alembic.set_main_option("script_location", str(package / "migrations"))
    alembic.set_main_option(
        "sqlalchemy.url", TEST_URL.replace("postgresql://", "postgresql+psycopg://")
    )
    command.upgrade(alembic, "head")
    with connect(TEST_URL) as connection:
        connection.execute("TRUNCATE rag.chunks, rag.documents, rag.ingestion_runs")
        connection.commit()
    temp = tmp_path_factory.mktemp("reranking-integration")
    ingest(
        IngestionConfig(
            repository=ROOT,
            corpus_root=ROOT / "rag" / "knowledge",
            runtime_root=temp / "ingestion",
            database_url=TEST_URL,
            embedding_dimension=384,
            target_tokens=400,
            overlap_tokens=60,
        ),
        FakeEmbeddingProvider(384),
    )
    retrieval = RetrievalConfig(
        repository=ROOT,
        database_url=TEST_URL,
        runtime_root=temp / "retrieval",
        evaluation_root=ROOT / "rag" / "evaluation",
    )
    reranking = RerankingConfig(
        repository=ROOT,
        runtime_root=temp / "reranking",
        evaluation_root=ROOT / "rag" / "evaluation",
        model_cache=temp / "models",
    )
    context = connect(TEST_URL)
    connection = context.__enter__()
    instance = RerankingPipeline(
        reranking,
        HybridRetriever(
            retrieval,
            RetrievalRepository(connection),
            FakeEmbeddingProvider(384),
        ),
        FakeRerankerProvider(),
    )
    yield instance
    context.__exit__(None, None, None)


def test_ingest_hybrid_rerank_and_evidence_selection(pipeline: RerankingPipeline) -> None:
    run = pipeline.rerank_query("database sessions wait while retries multiply")
    assert len(run.candidates) == 10
    assert len(run.results) == 10
    evidence = run.results[: pipeline.config.evidence_k]
    assert len(evidence) == 5
    assert {item.chunk.chunk_id for item in evidence} <= {
        item.chunk.chunk_id for item in run.candidates
    }
    assert all(item.retrieval.bm25_rank or item.retrieval.dense_rank for item in evidence)


def test_new_qrels_resolve_against_real_pgvector_snapshot(
    pipeline: RerankingPipeline,
) -> None:
    benchmark = load_benchmark(
        ROOT / "rag" / "evaluation" / "reranking_queries_v1.jsonl",
        ROOT / "rag" / "evaluation" / "reranking_qrels_v1.jsonl",
    )
    validate_qrels(benchmark, pipeline.retriever.snapshot)
    assert pipeline.retriever.snapshot.fingerprint
