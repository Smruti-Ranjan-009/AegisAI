from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from aegis_rag_retrieval.benchmark import (
    Benchmark,
    benchmark_id,
    validate_qrels,
)
from aegis_rag_retrieval.contracts import SearchFilters
from aegis_rag_retrieval.errors import BenchmarkError
from aegis_rag_retrieval.metrics import (
    aggregate_metrics,
    grouped_metrics,
    latency_summary,
    query_metrics,
)
from aegis_rag_retrieval.retriever import HybridRetriever


def evaluate(
    retriever: HybridRetriever,
    benchmark: Benchmark,
    *,
    split: str,
    output_root: Path,
    confirm_final_test: bool = False,
) -> dict[str, Any]:
    validate_qrels(benchmark, retriever.snapshot)
    identity, config_hash = benchmark_id(
        benchmark,
        corpus_fingerprint=retriever.snapshot.fingerprint,
        retrieval_contract=retriever.config.retrieval_contract(),
    )
    output = output_root / identity
    output.mkdir(parents=True, exist_ok=True)
    frozen_path = output / "frozen_manifest.json"
    frozen = _frozen_manifest(retriever, benchmark, identity, config_hash)
    if split == "development":
        _write_json(frozen_path, frozen)
    elif split == "test":
        if not confirm_final_test:
            raise BenchmarkError("final test requires --confirm-final-test")
        if not frozen_path.is_file():
            raise BenchmarkError("run development evaluation to freeze benchmark inputs first")
        if json.loads(frozen_path.read_text(encoding="utf-8")) != frozen:
            raise BenchmarkError("frozen benchmark inputs changed before final test")
        if (output / "test-report.json").exists():
            raise BenchmarkError("final test report already exists; refusing a repeated test run")

    queries = benchmark.selected(split)
    if not queries:
        raise BenchmarkError(f"benchmark split has no queries: {split}")
    retriever.retrieve_branches(queries[0].query)
    started = perf_counter()
    method_records: dict[str, list[dict[str, Any]]] = {
        "bm25": [],
        "dense": [],
        "hybrid": [],
    }
    latency: dict[str, list[float]] = {
        "bm25_seconds": [],
        "query_embedding_seconds": [],
        "dense_sql_seconds": [],
        "rrf_seconds": [],
        "total_seconds": [],
        "bm25_method_seconds": [],
        "dense_method_seconds": [],
        "hybrid_method_seconds": [],
    }
    complementarity: dict[int, Counter[str]] = {
        k: Counter() for k in (1, 3, 5, 10)
    }
    for query in queries:
        branches = retriever.retrieve_branches(query.query)
        grades = benchmark.grades_for(query.query_id, retriever.snapshot)
        for key, value in branches.timings.items():
            latency[key].append(value)
        latency["bm25_method_seconds"].append(branches.timings["bm25_seconds"])
        latency["dense_method_seconds"].append(
            branches.timings["query_embedding_seconds"]
            + branches.timings["dense_sql_seconds"]
        )
        latency["hybrid_method_seconds"].append(branches.timings["total_seconds"])
        for method in method_records:
            hits = branches.hits(method, limit=10)
            ranked_ids = [hit.chunk.chunk_id for hit in hits]
            method_records[method].append(
                {
                    "query_id": query.query_id,
                    "query": query.query,
                    "incident_type": query.incident_type,
                    "style": query.style,
                    "metrics": query_metrics(ranked_ids, grades),
                    "results": [hit.to_dict() for hit in hits],
                }
            )
        for k in complementarity:
            bm25_hit = method_records["bm25"][-1]["metrics"][f"hit@{k}"] > 0
            dense_hit = method_records["dense"][-1]["metrics"][f"hit@{k}"] > 0
            category = (
                "both"
                if bm25_hit and dense_hit
                else "bm25_only"
                if bm25_hit
                else "dense_only"
                if dense_hit
                else "neither"
            )
            complementarity[k][category] += 1

    retriever.assert_snapshot_unchanged()
    report = {
        **frozen,
        "split": split,
        "query_count": len(queries),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": perf_counter() - started,
        "primary_evaluation": "unfiltered query text only",
        "bm25_index_build_seconds": retriever.bm25.build_seconds,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "processor": platform.processor() or "unknown",
        },
        "metrics": {
            method: {
                "overall": aggregate_metrics(row["metrics"] for row in rows),
                "by_incident_type": grouped_metrics(rows, "incident_type"),
                "by_query_style": grouped_metrics(rows, "style"),
            }
            for method, rows in method_records.items()
        },
        "complementarity": {
            f"at_{k}": dict(sorted(counts.items()))
            for k, counts in complementarity.items()
        },
        "latency": {name: latency_summary(values) for name, values in latency.items()},
        "queries": method_records,
    }
    _write_json(output / f"{split}-report.json", report)
    (output / f"{split}-report.md").write_text(
        _markdown_report(report), encoding="utf-8"
    )
    return report


def evaluate_filter_cases(
    retriever: HybridRetriever,
    path: Path,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    results: list[dict[str, Any]] = []
    for case in cases:
        raw_filters = case["filters"]
        filters = SearchFilters.validated(
            services=raw_filters.get("services", []),
            incident_types=raw_filters.get("incident_types", []),
            document_types=raw_filters.get("document_types", []),
        )
        response = retriever.search(
            case["query"], method="hybrid", top_k=top_k, filters=filters
        )
        sources = [item["source_path"] for item in response["results"]]
        results.append(
            {
                "case_id": case["case_id"],
                "expected_source_path": case["expected_source_path"],
                "hit": case["expected_source_path"] in sources,
                "sources": sources,
            }
        )
    return {
        "case_count": len(results),
        "hit_rate": sum(item["hit"] for item in results) / len(results),
        "results": results,
    }


def _frozen_manifest(
    retriever: HybridRetriever,
    benchmark: Benchmark,
    identity: str,
    config_hash: str,
) -> dict[str, Any]:
    return {
        "benchmark_id": identity,
        "benchmark_schema_version": 1,
        "query_hash": benchmark.query_hash,
        "qrel_hash": benchmark.qrel_hash,
        "retrieval_config_hash": config_hash,
        "corpus_fingerprint": retriever.snapshot.fingerprint,
        "active_documents": retriever.snapshot.active_documents,
        "active_chunks": len(retriever.snapshot.chunks),
        "retrieval_contract": retriever.config.retrieval_contract(),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Retrieval benchmark — {report['split']}",
        "",
        f"- Benchmark: `{report['benchmark_id']}`",
        f"- Corpus fingerprint: `{report['corpus_fingerprint']}`",
        f"- Queries: {report['query_count']}",
        f"- Primary protocol: {report['primary_evaluation']}",
        "",
        "| Method | Recall@5 | MRR@10 | NDCG@10 |",
        "|---|---:|---:|---:|",
    ]
    for method in ("bm25", "dense", "hybrid"):
        metrics = report["metrics"][method]["overall"]
        lines.append(
            f"| {method} | {metrics['recall@5']:.3f} | "
            f"{metrics['mrr@10']:.3f} | {metrics['ndcg@10']:.3f} |"
        )
    lines.extend(
        (
            "",
            "Primary metric: NDCG@10. Reports are generated under ignored runtime storage.",
            "",
        )
    )
    return "\n".join(lines)
