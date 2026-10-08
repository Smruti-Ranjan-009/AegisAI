from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from aegis_rag_ingestion.contracts import EmbeddedChunk, SourceDocument


class KnowledgeRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def start_run(self, run_id: str, manifest: dict[str, Any]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rag.ingestion_runs
                    (id, status, started_at, model_id, embedding_dimension,
                     embeddings_normalized, chunk_config, manifest)
                VALUES (%s, 'running', %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    datetime.now(UTC),
                    manifest["embedding"]["model_id"],
                    manifest["embedding"]["dimension"],
                    manifest["embedding"]["normalized"],
                    Jsonb(manifest["chunking"]),
                    Jsonb(manifest),
                ),
            )

    def existing_documents(self) -> dict[str, dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT d.id, d.checksum, d.active,
                       (SELECT count(*) FROM rag.chunks c WHERE c.document_id = d.id)
                           AS chunk_count
                FROM rag.documents d
                """
            )
            return {row["id"]: row for row in cursor.fetchall()}

    def replace_document(
        self, document: SourceDocument, chunks: Sequence[EmbeddedChunk]
    ) -> None:
        metadata = document.metadata
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rag.documents
                    (id, source_path, title, document_type, version, checksum, synthetic,
                     services, incident_types, metadata, active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, now(), now())
                ON CONFLICT (id) DO UPDATE SET
                    source_path = EXCLUDED.source_path,
                    title = EXCLUDED.title,
                    document_type = EXCLUDED.document_type,
                    version = EXCLUDED.version,
                    checksum = EXCLUDED.checksum,
                    synthetic = EXCLUDED.synthetic,
                    services = EXCLUDED.services,
                    incident_types = EXCLUDED.incident_types,
                    metadata = EXCLUDED.metadata,
                    active = true,
                    updated_at = now()
                """,
                (
                    document.document_id,
                    document.source_path,
                    metadata.title,
                    metadata.document_type,
                    metadata.version,
                    document.checksum,
                    metadata.synthetic,
                    list(metadata.services),
                    list(metadata.incident_types),
                    Jsonb(
                        {
                            "title": metadata.title,
                            "document_type": metadata.document_type,
                            "version": metadata.version,
                            "services": metadata.services,
                            "incident_types": metadata.incident_types,
                            "synthetic": metadata.synthetic,
                        }
                    ),
                ),
            )
            cursor.execute("DELETE FROM rag.chunks WHERE document_id = %s", (document.document_id,))
            cursor.executemany(
                """
                INSERT INTO rag.chunks
                    (id, document_id, chunk_index, heading_path, content, embedded_text,
                     token_count, embedding, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                """,
                [
                    (
                        chunk.draft.chunk_id,
                        document.document_id,
                        chunk.draft.index,
                        list(chunk.draft.heading_path),
                        chunk.draft.content,
                        chunk.draft.embedded_text,
                        chunk.draft.token_count,
                        np.asarray(chunk.embedding, dtype=np.float32),
                        Jsonb({"source_path": document.source_path}),
                    )
                    for chunk in chunks
                ],
            )

    def reactivate(self, document_id: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE rag.documents SET active = true, updated_at = now() WHERE id = %s",
                (document_id,),
            )

    def deactivate_missing(self, current_ids: set[str]) -> int:
        with self.connection.cursor() as cursor:
            if current_ids:
                cursor.execute(
                    """
                    UPDATE rag.documents SET active = false, updated_at = now()
                    WHERE active = true AND NOT (id = ANY(%s))
                    """,
                    (list(current_ids),),
                )
            else:
                cursor.execute(
                    """
                    UPDATE rag.documents SET active = false, updated_at = now()
                    WHERE active = true
                    """
                )
            return cursor.rowcount

    def complete_run(
        self,
        run_id: str,
        counts: dict[str, int],
        quality: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE rag.ingestion_runs
                SET status = 'completed', completed_at = now(), counts = %s,
                    quality = %s, manifest = %s
                WHERE id = %s
                """,
                (Jsonb(counts), Jsonb(quality), Jsonb(manifest), run_id),
            )

    def versions(self) -> dict[str, str]:
        with self.connection.cursor() as cursor:
            pgvector_version = cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()[0]
            schema_version = cursor.execute(
                "SELECT version_num FROM rag.alembic_version"
            ).fetchone()[0]
        return {
            "schema_version": schema_version,
            "pgvector_version": pgvector_version,
        }

    def fail_run(self, run_id: str, message: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE rag.ingestion_runs
                SET status = 'failed', completed_at = now(), errors = %s
                WHERE id = %s
                """,
                (Jsonb([message]), run_id),
            )

    def status(self) -> dict[str, Any]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    count(*) FILTER (WHERE active) AS active_documents,
                    count(*) FILTER (WHERE NOT active) AS inactive_documents,
                    (SELECT count(*) FROM rag.chunks) AS chunks
                FROM rag.documents
                """
            )
            counts = dict(cursor.fetchone())
            cursor.execute(
                """
                SELECT id, status, started_at, completed_at, model_id,
                       embedding_dimension, counts
                FROM rag.ingestion_runs ORDER BY started_at DESC LIMIT 1
                """
            )
            latest = cursor.fetchone()
            cursor.execute(
                """
                SELECT document_type, count(*) AS count
                FROM rag.documents WHERE active
                GROUP BY document_type ORDER BY document_type
                """
            )
            document_types = {row["document_type"]: row["count"] for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT id, completed_at, model_id, embedding_dimension, counts
                FROM rag.ingestion_runs
                WHERE status = 'completed'
                ORDER BY completed_at DESC LIMIT 1
                """
            )
            latest_successful = cursor.fetchone()
        return {
            "counts": counts,
            "document_types": document_types,
            "latest_run": dict(latest) if latest else None,
            "latest_successful_run": dict(latest_successful) if latest_successful else None,
        }

    def validate_store(self, expected_dimension: int) -> dict[str, Any]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT count(*) AS chunk_count,
                       count(DISTINCT c.document_id) FILTER (WHERE d.active)
                           AS active_chunk_documents,
                       count(*) FILTER (WHERE vector_dims(c.embedding) <> %s)
                           AS wrong_dimensions,
                       count(*) FILTER (WHERE vector_norm(c.embedding) < 0.999
                                          OR vector_norm(c.embedding) > 1.001)
                           AS unnormalized,
                       count(*) FILTER (WHERE NOT length(trim(c.content)) > 0) AS empty_chunks
                FROM rag.chunks c
                JOIN rag.documents d ON d.id = c.document_id
                """,
                (expected_dimension,),
            )
            vector_checks = dict(cursor.fetchone())
            cursor.execute("SELECT count(*) AS active_documents FROM rag.documents WHERE active")
            active = cursor.fetchone()["active_documents"]
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'rag'
                  AND table_name IN ('documents', 'chunks', 'ingestion_runs')
                """
            )
            tables = sorted(row["table_name"] for row in cursor.fetchall())
            cursor.execute(
                """
                SELECT count(*) AS orphan_chunks
                FROM rag.chunks c LEFT JOIN rag.documents d ON d.id = c.document_id
                WHERE d.id IS NULL
                """
            )
            orphan_chunks = cursor.fetchone()["orphan_chunks"]
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            extension = cursor.fetchone()
            cursor.execute("SELECT version_num FROM rag.alembic_version")
            revision = cursor.fetchone()["version_num"]
        valid = (
            vector_checks["chunk_count"] > 0
            and vector_checks["wrong_dimensions"] == 0
            and vector_checks["unnormalized"] == 0
            and vector_checks["empty_chunks"] == 0
            and vector_checks["active_chunk_documents"] == active
            and tables == ["chunks", "documents", "ingestion_runs"]
            and orphan_chunks == 0
            and extension is not None
        )
        return {
            "valid": valid,
            "schema": "rag",
            "schema_revision": revision,
            "required_tables": tables,
            "pgvector_version": extension["extversion"] if extension else None,
            "orphan_chunks": orphan_chunks,
            "active_documents": active,
            **vector_checks,
        }

    def exact_smoke_query(self, vector: tuple[float, ...], limit: int = 3) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT c.id, d.source_path, c.heading_path,
                       c.embedding <=> %s AS cosine_distance
                FROM rag.chunks c
                JOIN rag.documents d ON d.id = c.document_id
                WHERE d.active
                ORDER BY c.embedding <=> %s
                LIMIT %s
                """,
                (
                    np.asarray(vector, dtype=np.float32),
                    np.asarray(vector, dtype=np.float32),
                    limit,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]
