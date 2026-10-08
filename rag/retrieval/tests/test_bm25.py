from helpers import chunk

from aegis_rag_retrieval.bm25 import BM25Index
from aegis_rag_retrieval.contracts import SearchFilters


def test_bm25_ranks_specific_operational_terms_and_filters() -> None:
    chunks = (
        chunk(
            "b",
            "Inspect the connection_pool when PostgreSQL acquisition time rises.",
            services=("postgresql",),
            incident_types=("dependency_failure",),
        ),
        chunk(
            "a",
            "Check CPU throttling and preserve a bounded profile.",
            services=("ad",),
            incident_types=("cpu_saturation",),
        ),
        chunk("c", "Validate recovery over a stable observation window."),
        chunk("d", "Preserve deployment evidence before making changes."),
    )
    index = BM25Index(chunks)
    results = index.search(
        "PostgreSQL connection_pool",
        limit=4,
        filters=SearchFilters(),
    )
    assert results[0].chunk.chunk_id == "b"
    assert index.k1 == 1.5
    assert index.b == 0.75
    filtered = index.search(
        "PostgreSQL connection_pool",
        limit=4,
        filters=SearchFilters.validated(services=["ad"]),
    )
    assert [item.chunk.chunk_id for item in filtered] == ["a"]


def test_bm25_zero_score_ties_use_chunk_id() -> None:
    index = BM25Index((chunk("z", "alpha"), chunk("a", "beta")))
    results = index.search("absent", limit=2, filters=SearchFilters())
    assert [result.chunk.chunk_id for result in results] == ["a", "z"]
