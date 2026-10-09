from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from aegis_rag_retrieval.metrics import (
    aggregate_metrics,
    grouped_metrics,
    latency_summary,
    query_metrics,
)

from aegis_rag_reranking.benchmark import (
    RerankingBenchmark,
    benchmark_id,
    validate_qrels,
)
from aegis_rag_reranking.errors import RerankingBenchmarkError
from aegis_rag_reranking.reranker import RerankingPipeline


def evaluate(
    pipeline: RerankingPipeline,
    benchmark: RerankingBenchmark,
    *,
    split: str,
    output_root: Path,
    confirm_final: bool = False,
) -> dict[str, Any]:
    validate_qrels(benchmark, pipeline.retriever.snapshot)
    contract = pipeline.config.contract(pipeline.retriever.config.retrieval_contract())
    identity, config_hash = benchmark_id(
        benchmark,
        corpus_fingerprint=pipeline.retriever.snapshot.fingerprint,
        contract=contract,
    )
    output = output_root / identity
    output.mkdir(parents=True, exist_ok=True)
    frozen = _frozen_manifest(pipeline, benchmark, identity, config_hash, contract)
    frozen_path = output / "frozen_manifest.json"
    if split == "development":
        _write_json(frozen_path, frozen)
    elif split == "final":
        if not confirm_final:
            raise RerankingBenchmarkError("final evaluation requires --confirm-final")
        if not frozen_path.is_file():
            raise RerankingBenchmarkError("run development evaluation to freeze inputs first")
        if json.loads(frozen_path.read_text(encoding="utf-8")) != frozen:
            raise RerankingBenchmarkError("frozen reranking inputs changed before final")
        if (output / "final-report.json").exists():
            raise RerankingBenchmarkError("final report exists; refusing repeated evaluation")
    else:
        raise RerankingBenchmarkError(f"unsupported benchmark split: {split}")

    queries = benchmark.selected(split)
    pipeline.rerank_query(queries[0].query)
    started = perf_counter()
    records: dict[str, list[dict[str, Any]]] = {"hybrid": [], "reranked": []}
    rerank_latencies: list[float] = []
    overall_latencies: list[float] = []
    retrieval_latencies: list[float] = []
    for query in queries:
        run = pipeline.rerank_query(query.query)
        grades = benchmark.grades_for(query.query_id, pipeline.retriever.snapshot)
        baseline_ids = [hit.chunk.chunk_id for hit in run.candidates]
        reranked_ids = [hit.chunk.chunk_id for hit in run.results]
        for method, ranked_ids, results in (
            (
                "hybrid",
                baseline_ids,
                [hit.to_dict() for hit in run.candidates],
            ),
            (
                "reranked",
                reranked_ids,
                [hit.to_dict() for hit in run.results],
            ),
        ):
            records[method].append(
                {
                    "query_id": query.query_id,
                    "query": query.query,
                    "incident_type": query.incident_type,
                    "style": query.style,
                    "metrics": query_metrics(ranked_ids, grades),
                    "results": results,
                }
            )
        rerank_latencies.append(run.timings["reranker_seconds"])
        retrieval_latencies.append(run.timings["retrieval_total_seconds"])
        overall_latencies.append(run.timings["total_seconds"])

    report = {
        **frozen,
        "split": split,
        "query_count": len(queries),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": perf_counter() - started,
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
            for method, rows in records.items()
        },
        "latency": {
            "model_load_seconds": pipeline.provider.load_seconds,
            "retrieval": latency_summary(retrieval_latencies),
            "reranker_10_passages": latency_summary(rerank_latencies),
            "retrieval_plus_reranker": latency_summary(overall_latencies),
        },
        "queries": records,
    }
    _write_json(output / f"{split}-report.json", report)
    (output / f"{split}-report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _frozen_manifest(
    pipeline: RerankingPipeline,
    benchmark: RerankingBenchmark,
    identity: str,
    config_hash: str,
    contract: dict[str, object],
) -> dict[str, Any]:
    snapshot = pipeline.retriever.snapshot
    return {
        "benchmark_id": identity,
        "benchmark_schema_version": 1,
        "query_hash": benchmark.query_hash,
        "qrel_hash": benchmark.qrel_hash,
        "configuration_hash": config_hash,
        "corpus_fingerprint": snapshot.fingerprint,
        "active_documents": snapshot.active_documents,
        "active_chunks": len(snapshot.chunks),
        "contract": contract,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Reranking benchmark — {report['split']}",
        "",
        f"- Benchmark: `{report['benchmark_id']}`",
        f"- Corpus: `{report['corpus_fingerprint']}`",
        f"- Queries: {report['query_count']}",
        "",
        "| Method | Recall@5 | Hit@5 | MRR@10 | NDCG@5 | NDCG@10 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in ("hybrid", "reranked"):
        metric = report["metrics"][method]["overall"]
        lines.append(
            f"| {method} | {metric['recall@5']:.3f} | {metric['hit@5']:.3f} | "
            f"{metric['mrr@10']:.3f} | {metric['ndcg@5']:.3f} | "
            f"{metric['ndcg@10']:.3f} |"
        )
    return "\n".join(lines) + "\n"
