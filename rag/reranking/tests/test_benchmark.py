from collections import Counter
from pathlib import Path

from aegis_rag_reranking.benchmark import load_benchmark

ROOT = Path(__file__).resolve().parents[3]


def test_committed_benchmark_has_frozen_balanced_structure() -> None:
    benchmark = load_benchmark(
        ROOT / "rag" / "evaluation" / "reranking_queries_v1.jsonl",
        ROOT / "rag" / "evaluation" / "reranking_qrels_v1.jsonl",
    )
    assert len(benchmark.queries) == 30
    assert len(benchmark.qrels) == 60
    assert len(benchmark.selected("development")) == 20
    final = benchmark.selected("final")
    assert len(final) == 10
    assert set(Counter(query.incident_type for query in final).values()) == {2}
    assert set(Counter(query.style for query in final).values()) == {2}
    assert len(benchmark.query_hash) == 64
    assert len(benchmark.qrel_hash) == 64


def test_phase_10_queries_do_not_duplicate_phase_9_queries() -> None:
    phase_10 = load_benchmark(
        ROOT / "rag" / "evaluation" / "reranking_queries_v1.jsonl",
        ROOT / "rag" / "evaluation" / "reranking_qrels_v1.jsonl",
    )
    phase_9_queries = {
        __import__("json").loads(line)["query"]
        for line in (ROOT / "rag" / "evaluation" / "retrieval_queries_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    assert not ({query.query for query in phase_10.queries} & phase_9_queries)
