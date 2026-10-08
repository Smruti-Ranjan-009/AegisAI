from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row

from aegis_rag_retrieval.contracts import (
    ChunkRecord,
    CorpusSnapshot,
    RankedChunk,
    SearchFilters,
)


def corpus_fingerprint(chunks: Sequence[ChunkRecord]) -> str:
    documents = sorted(
        {(chunk.document_id, chunk.document_checksum) for chunk in chunks},
        key=lambda item: item[0],
    )
    payload = {
        "documents": documents,
        "chunks": sorted(chunk.chunk_id for chunk in chunks),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _chunk_from_row(row: dict[str, Any]) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        document_checksum=row["document_checksum"],
        source_path=row["source_path"],
        title=row["title"],
        document_type=row["document_type"],
        services=tuple(row["services"]),
        incident_types=tuple(row["incident_types"]),
        heading_path=tuple(row["heading_path"]),
        content=row["content"],
    )


class RetrievalRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def load_active_snapshot(self) -> CorpusSnapshot:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, d.checksum AS document_checksum,
                       d.source_path, d.title, d.document_type, d.services,
                       d.incident_types, c.heading_path, c.content
                FROM rag.chunks c
                JOIN rag.documents d ON d.id = c.document_id
                WHERE d.active
                ORDER BY c.id
                """
            )
            chunks = tuple(_chunk_from_row(dict(row)) for row in cursor.fetchall())
        return CorpusSnapshot(
            fingerprint=corpus_fingerprint(chunks),
            chunks=chunks,
            active_documents=len({chunk.document_id for chunk in chunks}),
        )

    def current_fingerprint(self) -> str:
        return self.load_active_snapshot().fingerprint

    def dense_search(
        self,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: SearchFilters,
    ) -> tuple[RankedChunk, ...]:
        clauses = ["d.active"]
        query_vector = np.asarray(vector, dtype=np.float32)
        parameters: list[Any] = [query_vector]
        if filters.services:
            clauses.append("d.services && %s::text[]")
            parameters.append(list(filters.services))
        if filters.incident_types:
            clauses.append("d.incident_types && %s::text[]")
            parameters.append(list(filters.incident_types))
        if filters.document_types:
            clauses.append("d.document_type = ANY(%s::text[])")
            parameters.append(list(filters.document_types))
        parameters.extend((query_vector, limit))
        statement = f"""
            SELECT c.id AS chunk_id, c.document_id, d.checksum AS document_checksum,
                   d.source_path, d.title, d.document_type, d.services,
                   d.incident_types, c.heading_path, c.content,
                   1.0 - (c.embedding <=> %s) AS similarity
            FROM rag.chunks c
            JOIN rag.documents d ON d.id = c.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY c.embedding <=> %s, c.id
            LIMIT %s
        """
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
        return tuple(
            RankedChunk(_chunk_from_row(dict(row)), rank, float(row["similarity"]))
            for rank, row in enumerate(rows, start=1)
        )
