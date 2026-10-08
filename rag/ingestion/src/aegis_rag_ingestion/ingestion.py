from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from aegis_rag_ingestion.chunking import chunk_corpus
from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.contracts import EmbeddedChunk, EmbeddingProvider
from aegis_rag_ingestion.database import connect
from aegis_rag_ingestion.embeddings import validate_vectors
from aegis_rag_ingestion.manifest import build_manifest, write_run_outputs
from aegis_rag_ingestion.parsing import discover_documents
from aegis_rag_ingestion.quality import build_quality_report
from aegis_rag_ingestion.repository import KnowledgeRepository


def inspect_corpus(config: IngestionConfig, provider: EmbeddingProvider) -> dict[str, Any]:
    documents = discover_documents(config.corpus_root)
    chunks = chunk_corpus(
        documents,
        provider.tokenizer,
        target_tokens=config.target_tokens,
        overlap_tokens=config.overlap_tokens,
        minimum_tokens=config.minimum_chunk_tokens,
        schema_version=config.chunk_schema_version,
    )
    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "document_types": sorted({document.metadata.document_type for document in documents}),
        "services": sorted({item for document in documents for item in document.metadata.services}),
        "incident_types": sorted(
            {item for document in documents for item in document.metadata.incident_types}
        ),
        "sources": [
            {
                "source_path": document.source_path,
                "document_id": document.document_id,
                "checksum": document.checksum,
            }
            for document in documents
        ],
        "validation_problems": [],
        "tokenizer": provider.tokenizer.identity,
        "token_count": sum(chunk.token_count for chunk in chunks),
    }


def ingest(config: IngestionConfig, provider: EmbeddingProvider) -> dict[str, Any]:
    overall_started = time.perf_counter()
    if provider.dimension != config.embedding_dimension:
        raise ValueError(
            f"provider dimension {provider.dimension} does not match {config.embedding_dimension}"
        )
    documents = discover_documents(config.corpus_root)
    chunks = chunk_corpus(
        documents,
        provider.tokenizer,
        target_tokens=config.target_tokens,
        overlap_tokens=config.overlap_tokens,
        minimum_tokens=config.minimum_chunk_tokens,
        schema_version=config.chunk_schema_version,
    )
    corpus_digest = hashlib.sha256(
        "".join(document.checksum for document in documents).encode()
    ).hexdigest()[:12]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"{timestamp}-{corpus_digest}"
    manifest = build_manifest(run_id, config, provider, documents)

    database_seconds = 0.0
    database_started = time.perf_counter()
    with connect(config.database_url) as connection:
        repository = KnowledgeRepository(connection)
        repository.start_run(run_id, manifest)
        connection.commit()
        existing = repository.existing_documents()
    database_seconds += time.perf_counter() - database_started
    parse_chunk_seconds = time.perf_counter() - overall_started - database_seconds

    changed_ids = {
        document.document_id
        for document in documents
        if document.document_id not in existing
        or existing[document.document_id]["checksum"] != document.checksum
    }
    changed_chunks = [chunk for chunk in chunks if chunk.document_id in changed_ids]
    embedding_started = time.perf_counter()
    try:
        vectors = provider.embed_documents([chunk.embedded_text for chunk in changed_chunks])
        validate_vectors(vectors, provider.dimension, normalized=provider.normalized)
    except Exception as exc:
        with connect(config.database_url) as connection:
            KnowledgeRepository(connection).fail_run(run_id, str(exc))
            connection.commit()
        raise
    embedding_seconds = time.perf_counter() - embedding_started
    embedded = tuple(
        EmbeddedChunk(draft=chunk, embedding=vector)
        for chunk, vector in zip(changed_chunks, vectors, strict=True)
    )
    embedded_by_document: dict[str, list[EmbeddedChunk]] = defaultdict(list)
    for chunk in embedded:
        embedded_by_document[chunk.draft.document_id].append(chunk)

    counts = {
        "documents_discovered": len(documents),
        "documents_inserted": sum(document.document_id not in existing for document in documents),
        "documents_updated": sum(
            document.document_id in existing and document.document_id in changed_ids
            for document in documents
        ),
        "documents_skipped": len(documents) - len(changed_ids),
        "documents_unchanged": len(documents) - len(changed_ids),
        "documents_reactivated": sum(
            document.document_id in existing
            and not existing[document.document_id]["active"]
            and document.document_id not in changed_ids
            for document in documents
        ),
        "documents_deactivated": 0,
        "chunks_written": len(embedded),
        "chunks_inserted": len(embedded),
        "chunks_removed": sum(
            existing[document_id]["chunk_count"]
            for document_id in changed_ids
            if document_id in existing
        ),
    }
    quality = build_quality_report(
        documents, chunks, embedded, expected_dimension=config.embedding_dimension
    )
    if (
        not quality["chunks"]
        or quality["empty_chunks"]
        or quality["embedding_dimension_mismatches"]
        or quality["non_finite_embeddings"]
    ):
        message = "serious quality validation failure"
        with connect(config.database_url) as connection:
            KnowledgeRepository(connection).fail_run(run_id, message)
            connection.commit()
        raise ValueError(message)

    try:
        database_started = time.perf_counter()
        with connect(config.database_url) as connection:
            repository = KnowledgeRepository(connection)
            for document in documents:
                if document.document_id in changed_ids:
                    repository.replace_document(
                        document, embedded_by_document[document.document_id]
                    )
                elif not existing[document.document_id]["active"]:
                    repository.reactivate(document.document_id)
            counts["documents_deactivated"] = repository.deactivate_missing(
                {document.document_id for document in documents}
            )
            database_seconds += time.perf_counter() - database_started
            versions = repository.versions()
            completed_at = datetime.now(UTC)
            duration_seconds = time.perf_counter() - overall_started
            performance = {
                "parse_chunk_seconds": round(parse_chunk_seconds, 6),
                "embedding_seconds": round(embedding_seconds, 6),
                "database_seconds": round(database_seconds, 6),
                "duration_seconds": round(duration_seconds, 6),
                "embedded_chunks_per_second": round(
                    len(embedded) / embedding_seconds, 3
                )
                if embedded
                else 0.0,
            }
            manifest.update(
                {
                    "completed_at": completed_at.isoformat(),
                    "completed_at_utc": completed_at.isoformat(),
                    "counts": counts,
                    "database": versions,
                    "performance": performance,
                }
            )
            repository.complete_run(run_id, counts, quality, manifest)
            connection.commit()
    except Exception as exc:
        with connect(config.database_url) as connection:
            KnowledgeRepository(connection).fail_run(run_id, str(exc))
            connection.commit()
        raise

    output_directory = write_run_outputs(config.runtime_root, run_id, manifest, quality)
    return {
        "run_id": run_id,
        "counts": counts,
        "quality": quality,
        "performance": performance,
        "output_directory": str(output_directory),
    }
