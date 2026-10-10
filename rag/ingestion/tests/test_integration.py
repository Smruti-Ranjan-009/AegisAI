from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.database import connect, require_isolated_test_database
from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider
from aegis_rag_ingestion.ingestion import ingest
from aegis_rag_ingestion.repository import KnowledgeRepository

TEST_URL = os.getenv("AEGIS_RAG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="AEGIS_RAG_TEST_DATABASE_URL is not set")

SOURCE = """---
title: Integration Guide
document_type: runbook
version: 1
services: [platform]
incident_types: [general]
synthetic: true
---
# Response
Check health, preserve evidence, and validate recovery signals.
"""


@pytest.fixture
def config(tmp_path: Path) -> IngestionConfig:
    assert TEST_URL is not None
    require_isolated_test_database(TEST_URL)
    package_root = Path(__file__).resolve().parents[1]
    alembic = Config(str(package_root / "alembic.ini"))
    alembic.set_main_option("script_location", str(package_root / "migrations"))
    alembic.set_main_option("sqlalchemy.url", TEST_URL.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(alembic, "head")
    with connect(TEST_URL) as connection:
        connection.execute("TRUNCATE rag.chunks, rag.documents, rag.ingestion_runs")
        connection.commit()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "guide.md").write_text(SOURCE, encoding="utf-8")
    return IngestionConfig(
        repository=tmp_path,
        corpus_root=corpus,
        runtime_root=tmp_path / "runtime",
        database_url=TEST_URL,
        embedding_dimension=384,
        target_tokens=20,
        overlap_tokens=4,
    )


def test_migration_extension_and_indexes(config: IngestionConfig) -> None:
    with connect(config.database_url) as connection:
        extension = connection.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'rag'"
            ).fetchall()
        }
    assert extension is not None
    assert "idx_rag_documents_services" in indexes
    assert not any("hnsw" in name or "ivfflat" in name for name in indexes)


def test_idempotency_update_inactive_and_atomic_failure(config: IngestionConfig) -> None:
    provider = FakeEmbeddingProvider(384)
    first = ingest(config, provider)
    second = ingest(config, provider)
    assert first["counts"]["documents_inserted"] == 1
    assert second["counts"]["documents_skipped"] == 1
    assert second["counts"]["chunks_written"] == 0
    assert first["performance"]["embedding_seconds"] >= 0
    manifest = json.loads(
        (Path(first["output_directory"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["completed_at_utc"]
    assert manifest["database"] == {
        "pgvector_version": "0.8.6",
        "schema_version": "0001_rag_vector_schema",
    }
    assert manifest["counts"]["documents_inserted"] == 1
    assert first["quality"]["empty_chunks"] == 0
    assert first["quality"]["embedding_dimension_mismatches"] == 0

    path = config.corpus_root / "guide.md"
    path.write_text(SOURCE.replace("version: 1", "version: 2"), encoding="utf-8")
    updated = ingest(config, provider)
    assert updated["counts"]["documents_updated"] == 1

    class FailingProvider(FakeEmbeddingProvider):
        def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
            raise RuntimeError("intentional embedding failure")

    path.write_text(SOURCE.replace("version: 1", "version: 3"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="intentional"):
        ingest(config, FailingProvider(384))
    with connect(config.database_url) as connection:
        stored_version = connection.execute("SELECT version FROM rag.documents").fetchone()[0]
    assert stored_version == 2

    path.unlink()
    empty = config.corpus_root / "replacement.md"
    empty.write_text(SOURCE.replace("Integration Guide", "Replacement Guide"), encoding="utf-8")
    missing = ingest(config, provider)
    assert missing["counts"]["documents_deactivated"] == 1
    with connect(config.database_url) as connection:
        repository = KnowledgeRepository(connection)
        status = repository.status()
        validation = repository.validate_store(384)
    assert status["counts"] == {"active_documents": 1, "inactive_documents": 1, "chunks": 2}
    assert validation["valid"] is True


def test_exact_vector_smoke_query(config: IngestionConfig) -> None:
    provider = FakeEmbeddingProvider(384)
    ingest(config, provider)
    with connect(config.database_url) as connection:
        repository = KnowledgeRepository(connection)
        validation = repository.validate_store(384)
        matches = repository.exact_smoke_query(provider.embed_query("service health"), limit=1)
    assert validation["valid"] is True
    assert len(matches) == 1
    assert matches[0]["cosine_distance"] >= 0
