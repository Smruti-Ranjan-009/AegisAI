from __future__ import annotations

from aegis_rag_retrieval.contracts import ChunkRecord


def chunk(
    chunk_id: str,
    content: str,
    *,
    source_path: str = "runbooks/example.md",
    title: str = "Example Runbook",
    document_id: str = "doc-1",
    checksum: str = "a" * 64,
    document_type: str = "runbook",
    services: tuple[str, ...] = ("platform",),
    incident_types: tuple[str, ...] = ("general",),
    heading_path: tuple[str, ...] = ("Example Runbook", "Triage"),
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=document_id,
        document_checksum=checksum,
        source_path=source_path,
        title=title,
        document_type=document_type,
        services=services,
        incident_types=incident_types,
        heading_path=heading_path,
        content=content,
    )

