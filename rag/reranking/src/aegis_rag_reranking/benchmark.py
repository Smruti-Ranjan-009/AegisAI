from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegis_rag_ingestion.contracts import INCIDENT_TYPES
from aegis_rag_retrieval.contracts import CorpusSnapshot

from aegis_rag_reranking.errors import RerankingBenchmarkError

QUERY_COUNT = 30
DEVELOPMENT_COUNT = 20
FINAL_COUNT = 10
STYLES = frozenset(
    {"symptom", "signal", "root_cause", "mitigation", "operational_question"}
)
TARGET_INCIDENTS = INCIDENT_TYPES - {"general"}


@dataclass(frozen=True)
class RerankingQuery:
    query_id: str
    query: str
    incident_type: str
    style: str
    split: str


@dataclass(frozen=True)
class RerankingQrel:
    query_id: str
    source_path: str
    heading_path: tuple[str, ...]
    grade: int


@dataclass(frozen=True)
class RerankingBenchmark:
    queries: tuple[RerankingQuery, ...]
    qrels: tuple[RerankingQrel, ...]
    query_hash: str
    qrel_hash: str

    def selected(self, split: str) -> tuple[RerankingQuery, ...]:
        if split not in {"development", "final"}:
            raise RerankingBenchmarkError(f"unsupported benchmark split: {split}")
        return tuple(query for query in self.queries if query.split == split)

    def grades_for(self, query_id: str, snapshot: CorpusSnapshot) -> dict[str, int]:
        lookup = {
            (chunk.source_path, chunk.heading_path): chunk.chunk_id for chunk in snapshot.chunks
        }
        return {
            lookup[(qrel.source_path, qrel.heading_path)]: qrel.grade
            for qrel in self.qrels
            if qrel.query_id == query_id
        }


def load_benchmark(query_path: Path, qrel_path: Path) -> RerankingBenchmark:
    benchmark = RerankingBenchmark(
        queries=tuple(_parse_query(item) for item in _load_jsonl(query_path)),
        qrels=tuple(_parse_qrel(item) for item in _load_jsonl(qrel_path)),
        query_hash=hashlib.sha256(query_path.read_bytes()).hexdigest(),
        qrel_hash=hashlib.sha256(qrel_path.read_bytes()).hexdigest(),
    )
    validate_structure(benchmark)
    return benchmark


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RerankingBenchmarkError(f"benchmark file does not exist: {path}")
    values: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RerankingBenchmarkError(f"invalid JSON at {path}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise RerankingBenchmarkError(f"JSONL entry must be an object at {path}:{number}")
        values.append(value)
    return values


def _parse_query(item: dict[str, Any]) -> RerankingQuery:
    expected = {"query_id", "query", "incident_type", "style", "split"}
    if set(item) != expected:
        raise RerankingBenchmarkError("reranking query fields do not match schema")
    if not all(isinstance(item[key], str) and item[key].strip() for key in expected):
        raise RerankingBenchmarkError("reranking query fields must be non-empty strings")
    return RerankingQuery(**item)


def _parse_qrel(item: dict[str, Any]) -> RerankingQrel:
    expected = {"query_id", "source_path", "heading_path", "grade"}
    if set(item) != expected:
        raise RerankingBenchmarkError("reranking qrel fields do not match schema")
    heading = item["heading_path"]
    if not isinstance(heading, list) or not heading or not all(
        isinstance(part, str) and part for part in heading
    ):
        raise RerankingBenchmarkError("qrel heading_path must be a non-empty string list")
    if item["grade"] not in {1, 2}:
        raise RerankingBenchmarkError("qrel grade must be 1 or 2")
    return RerankingQrel(
        query_id=item["query_id"],
        source_path=item["source_path"],
        heading_path=tuple(heading),
        grade=item["grade"],
    )


def validate_structure(benchmark: RerankingBenchmark) -> None:
    queries = benchmark.queries
    if len(queries) != QUERY_COUNT:
        raise RerankingBenchmarkError(f"expected {QUERY_COUNT} queries; found {len(queries)}")
    ids = [query.query_id for query in queries]
    if len(ids) != len(set(ids)):
        raise RerankingBenchmarkError("reranking query IDs must be unique")
    if Counter(query.split for query in queries) != {
        "development": DEVELOPMENT_COUNT,
        "final": FINAL_COUNT,
    }:
        raise RerankingBenchmarkError("split must contain 20 development and 10 final queries")
    if Counter(query.incident_type for query in queries) != Counter(
        {incident: 6 for incident in TARGET_INCIDENTS}
    ):
        raise RerankingBenchmarkError("each incident family must have exactly six queries")
    if Counter(query.style for query in queries) != Counter({style: 6 for style in STYLES}):
        raise RerankingBenchmarkError("each query style must have exactly six queries")
    final = [query for query in queries if query.split == "final"]
    if Counter(query.incident_type for query in final) != Counter(
        {incident: 2 for incident in TARGET_INCIDENTS}
    ):
        raise RerankingBenchmarkError("final split must have two queries per incident family")
    if Counter(query.style for query in final) != Counter({style: 2 for style in STYLES}):
        raise RerankingBenchmarkError("final split must have two queries per style")
    qrel_ids = {qrel.query_id for qrel in benchmark.qrels}
    if qrel_ids != set(ids):
        raise RerankingBenchmarkError("qrels must cover exactly the benchmark query IDs")
    if {qrel.query_id for qrel in benchmark.qrels if qrel.grade == 2} != set(ids):
        raise RerankingBenchmarkError("every query must have a grade-2 qrel")


def validate_qrels(benchmark: RerankingBenchmark, snapshot: CorpusSnapshot) -> None:
    available = {(chunk.source_path, chunk.heading_path) for chunk in snapshot.chunks}
    unresolved = [
        qrel
        for qrel in benchmark.qrels
        if (qrel.source_path, qrel.heading_path) not in available
    ]
    if unresolved:
        first = unresolved[0]
        raise RerankingBenchmarkError(
            "qrel does not resolve to the active corpus: "
            f"{first.query_id} {first.source_path} {list(first.heading_path)}"
        )


def benchmark_id(
    benchmark: RerankingBenchmark,
    *,
    corpus_fingerprint: str,
    contract: dict[str, object],
) -> tuple[str, str]:
    config_hash = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    identity = hashlib.sha256(
        "\0".join(
            (
                "reranking-benchmark-v1",
                benchmark.query_hash,
                benchmark.qrel_hash,
                corpus_fingerprint,
                config_hash,
            )
        ).encode()
    ).hexdigest()
    return f"reranking-v1-{identity[:12]}", config_hash
