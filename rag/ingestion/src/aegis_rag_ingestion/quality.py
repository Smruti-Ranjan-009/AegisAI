from __future__ import annotations

import math
from collections import Counter
from statistics import mean, median
from typing import Any

from aegis_rag_ingestion.contracts import ChunkDraft, EmbeddedChunk, SourceDocument


def build_quality_report(
    documents: tuple[SourceDocument, ...],
    chunks: tuple[ChunkDraft, ...],
    embedded_chunks: tuple[EmbeddedChunk, ...],
    *,
    expected_dimension: int,
) -> dict[str, Any]:
    token_counts = [chunk.token_count for chunk in chunks]
    content_counts = Counter(chunk.content for chunk in chunks)
    dimensions = Counter(len(chunk.embedding) for chunk in embedded_chunks)
    dimension_mismatches = sum(
        len(chunk.embedding) != expected_dimension for chunk in embedded_chunks
    )
    non_finite = sum(
        1
        for chunk in embedded_chunks
        if any(not math.isfinite(value) for value in chunk.embedding)
    )
    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "embedded_chunks": len(embedded_chunks),
        "document_types": dict(
            sorted(Counter(d.metadata.document_type for d in documents).items())
        ),
        "incident_types": dict(
            sorted(Counter(item for d in documents for item in d.metadata.incident_types).items())
        ),
        "services": dict(
            sorted(Counter(item for d in documents for item in d.metadata.services).items())
        ),
        "synthetic_documents": sum(document.metadata.synthetic for document in documents),
        "non_synthetic_documents": sum(
            not document.metadata.synthetic for document in documents
        ),
        "tokens": {
            "minimum": min(token_counts, default=0),
            "maximum": max(token_counts, default=0),
            "mean": round(mean(token_counts), 2) if token_counts else 0,
            "median": median(token_counts) if token_counts else 0,
            "p50": median(token_counts) if token_counts else 0,
            "p95": _percentile(token_counts, 0.95),
            "total": sum(token_counts),
        },
        "duplicate_chunk_contents": sum(
            count - 1 for count in content_counts.values() if count > 1
        ),
        "empty_chunks": sum(not chunk.content.strip() for chunk in chunks),
        "embedding_dimensions": {str(key): value for key, value in sorted(dimensions.items())},
        "embedding_dimension_mismatches": dimension_mismatches,
        "non_finite_embeddings": non_finite,
    }


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)
