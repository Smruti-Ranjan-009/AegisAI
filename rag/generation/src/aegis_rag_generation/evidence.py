from __future__ import annotations

from aegis_rag_reranking.contracts import RerankedHit

from aegis_rag_generation.contracts import EvidenceItem


def build_evidence_pack(
    results: tuple[RerankedHit, ...], *, limit: int = 5
) -> tuple[EvidenceItem, ...]:
    return tuple(
        EvidenceItem(
            evidence_id=f"E{index}",
            chunk_id=hit.chunk.chunk_id,
            source_path=hit.chunk.source_path,
            title=hit.chunk.title,
            heading_path=hit.chunk.heading_path,
            content=hit.chunk.content,
            reranked_rank=hit.reranked_rank,
        )
        for index, hit in enumerate(results[:limit], start=1)
    )
