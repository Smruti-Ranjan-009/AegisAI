import json
from collections import Counter
from pathlib import Path

import pytest

from aegis_rag_retrieval.benchmark import BenchmarkError, load_benchmark

ROOT = Path(__file__).resolve().parents[3]
QUERIES = ROOT / "rag" / "evaluation" / "retrieval_queries_v1.jsonl"
QRELS = ROOT / "rag" / "evaluation" / "retrieval_qrels_v1.jsonl"


def test_primary_benchmark_split_balance_and_no_filter_leakage() -> None:
    benchmark = load_benchmark(QUERIES, QRELS)
    assert len(benchmark.queries) == 50
    assert Counter(query.split for query in benchmark.queries) == {
        "development": 30,
        "test": 20,
    }
    assert Counter(
        query.incident_type for query in benchmark.queries if query.split == "test"
    ) == {
        "cpu_saturation": 4,
        "memory_leak": 4,
        "service_failure": 4,
        "dependency_failure": 4,
        "high_latency": 4,
    }
    raw = [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines()]
    assert all("filters" not in item and set(item) == {
        "query_id", "query", "incident_type", "style", "split"
    } for item in raw)


def test_benchmark_hash_and_schema_detect_changes(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.jsonl"
    queries.write_bytes(QUERIES.read_bytes())
    qrels.write_bytes(QRELS.read_bytes())
    original = load_benchmark(queries, qrels)
    lines = queries.read_text(encoding="utf-8").splitlines()
    value = json.loads(lines[0])
    value["query"] += " changed"
    lines[0] = json.dumps(value, separators=(",", ":"))
    queries.write_text("\n".join(lines) + "\n", encoding="utf-8")
    changed = load_benchmark(queries, qrels)
    assert changed.query_hash != original.query_hash

    value["filters"] = {"services": ["ad"]}
    lines[0] = json.dumps(value)
    queries.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(BenchmarkError, match="fields must be"):
        load_benchmark(queries, qrels)

