from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegis_rag_ingestion.contracts import INCIDENT_TYPES

from aegis_rag_retrieval.contracts import CorpusSnapshot
from aegis_rag_retrieval.errors import BenchmarkError

QUERY_COUNT = 50
DEVELOPMENT_COUNT = 30
TEST_COUNT = 20
STYLES = frozenset(
    {"symptom", "signal", "root_cause", "mitigation", "operational_question"}
)
TARGET_INCIDENTS = INCIDENT_TYPES - {"general"}


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    query: str
    incident_type: str
    style: str
    split: str


@dataclass(frozen=True)
class Qrel:
    query_id: str
    source_path: str
    heading_path: tuple[str, ...]
    grade: int


@dataclass(frozen=True)
class Benchmark:
    queries: tuple[BenchmarkQuery, ...]
    qrels: tuple[Qrel, ...]
    query_hash: str
    qrel_hash: str

    def selected(self, split: str) -> tuple[BenchmarkQuery, ...]:
        if split == "all":
            return self.queries
        if split not in {"development", "test"}:
            raise BenchmarkError(f"unsupported benchmark split: {split}")
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


def load_benchmark(query_path: Path, qrel_path: Path) -> Benchmark:
    queries_raw = _load_jsonl(query_path)
    qrels_raw = _load_jsonl(qrel_path)
    queries = tuple(_parse_query(item) for item in queries_raw)
    qrels = tuple(_parse_qrel(item) for item in qrels_raw)
    benchmark = Benchmark(
        queries=queries,
        qrels=qrels,
        query_hash=hashlib.sha256(query_path.read_bytes()).hexdigest(),
        qrel_hash=hashlib.sha256(qrel_path.read_bytes()).hexdigest(),
    )
    validate_structure(benchmark)
    return benchmark


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise BenchmarkError(f"benchmark file does not exist: {path}")
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise BenchmarkError(f"JSONL entry must be an object at {path}:{line_number}")
        values.append(item)
    return values


def _parse_query(item: dict[str, Any]) -> BenchmarkQuery:
    expected = {"query_id", "query", "incident_type", "style", "split"}
    if set(item) != expected:
        raise BenchmarkError(
            f"query {item.get('query_id', '<unknown>')} fields must be {sorted(expected)}"
        )
    if not all(isinstance(item[key], str) and item[key].strip() for key in expected):
        raise BenchmarkError("query fields must be non-empty strings")
    return BenchmarkQuery(**item)


def _parse_qrel(item: dict[str, Any]) -> Qrel:
    expected = {"query_id", "source_path", "heading_path", "grade"}
    if set(item) != expected:
        raise BenchmarkError(f"qrel fields must be {sorted(expected)}")
    heading = item["heading_path"]
    if not isinstance(heading, list) or not heading or not all(
        isinstance(part, str) and part for part in heading
    ):
        raise BenchmarkError("qrel heading_path must be a non-empty string list")
    if item["grade"] not in {1, 2}:
        raise BenchmarkError("qrel grade must be 1 or 2")
    return Qrel(
        query_id=item["query_id"],
        source_path=item["source_path"],
        heading_path=tuple(heading),
        grade=item["grade"],
    )


def validate_structure(benchmark: Benchmark) -> None:
    queries = benchmark.queries
    if len(queries) != QUERY_COUNT:
        raise BenchmarkError(f"expected {QUERY_COUNT} primary queries; found {len(queries)}")
    ids = [query.query_id for query in queries]
    if len(ids) != len(set(ids)):
        raise BenchmarkError("benchmark query IDs must be unique")
    if set(query.incident_type for query in queries) != TARGET_INCIDENTS:
        raise BenchmarkError("benchmark must cover exactly the five target incident types")
    if set(query.style for query in queries) != STYLES:
        raise BenchmarkError("benchmark must cover exactly the five query styles")
    if Counter(query.incident_type for query in queries) != Counter(
        {incident: 10 for incident in TARGET_INCIDENTS}
    ):
        raise BenchmarkError("each incident type must have exactly ten queries")
    if Counter(query.style for query in queries) != Counter({style: 10 for style in STYLES}):
        raise BenchmarkError("each query style must have exactly ten queries")
    split_counts = Counter(query.split for query in queries)
    if split_counts != {"development": DEVELOPMENT_COUNT, "test": TEST_COUNT}:
        raise BenchmarkError("benchmark split must contain 30 development and 20 test queries")
    test_incidents = Counter(
        query.incident_type for query in queries if query.split == "test"
    )
    if test_incidents != Counter({incident: 4 for incident in TARGET_INCIDENTS}):
        raise BenchmarkError("final test split must contain four queries per incident type")
    test_styles = Counter(query.style for query in queries if query.split == "test")
    if test_styles != Counter({style: 4 for style in STYLES}):
        raise BenchmarkError("final test split must contain four queries per query style")
    query_ids = set(ids)
    qrel_ids = {qrel.query_id for qrel in benchmark.qrels}
    if qrel_ids != query_ids:
        raise BenchmarkError("qrels must cover every query ID and no unknown IDs")
    grade_twos = {qrel.query_id for qrel in benchmark.qrels if qrel.grade == 2}
    if grade_twos != query_ids:
        raise BenchmarkError("every query must have at least one grade-2 qrel")


def validate_qrels(benchmark: Benchmark, snapshot: CorpusSnapshot) -> None:
    available = {(chunk.source_path, chunk.heading_path) for chunk in snapshot.chunks}
    unresolved = sorted(
        (qrel.query_id, qrel.source_path, qrel.heading_path)
        for qrel in benchmark.qrels
        if (qrel.source_path, qrel.heading_path) not in available
    )
    if unresolved:
        first = unresolved[0]
        raise BenchmarkError(
            "qrel does not resolve to an active chunk: "
            f"query={first[0]} source={first[1]} heading={list(first[2])}"
        )


def benchmark_id(
    benchmark: Benchmark,
    *,
    corpus_fingerprint: str,
    retrieval_contract: dict[str, object],
) -> tuple[str, str]:
    config_hash = hashlib.sha256(
        json.dumps(retrieval_contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    identity = hashlib.sha256(
        "\0".join(
            (
                "retrieval-benchmark-v1",
                benchmark.query_hash,
                benchmark.qrel_hash,
                corpus_fingerprint,
                config_hash,
            )
        ).encode()
    ).hexdigest()
    return f"retrieval-v1-{identity[:12]}", config_hash
