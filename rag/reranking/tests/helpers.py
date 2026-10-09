from __future__ import annotations

from aegis_rag_retrieval.contracts import ChunkRecord, RetrievalHit


def hit(
    chunk_id: str,
    content: str,
    *,
    rank: int,
    score: float = 0.01,
) -> RetrievalHit:
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        document_checksum="a" * 64,
        source_path=f"runbooks/{chunk_id}.md",
        title=f"Title {chunk_id}",
        document_type="runbook",
        services=("platform",),
        incident_types=("general",),
        heading_path=(f"Title {chunk_id}", "Triage"),
        content=content,
    )
    return RetrievalHit(
        chunk=chunk,
        rank=rank,
        score=score,
        bm25_rank=rank,
        bm25_score=score * 10,
        dense_rank=rank + 1,
        dense_score=score * 5,
    )
