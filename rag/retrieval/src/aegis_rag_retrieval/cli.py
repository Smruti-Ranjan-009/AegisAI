from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from aegis_rag_ingestion.database import connect
from aegis_rag_ingestion.embeddings import (
    FakeEmbeddingProvider,
    SentenceTransformerProvider,
)

from aegis_rag_retrieval.benchmark import load_benchmark, validate_qrels
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import SearchFilters
from aegis_rag_retrieval.errors import RetrievalError
from aegis_rag_retrieval.evaluation import evaluate, evaluate_filter_cases
from aegis_rag_retrieval.repository import RetrievalRepository
from aegis_rag_retrieval.retriever import HybridRetriever


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AegisAI offline hybrid retrieval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search the active knowledge snapshot")
    search.add_argument("query")
    search.add_argument("--method", choices=("bm25", "dense", "hybrid"), default="hybrid")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--service", action="append", default=[])
    search.add_argument("--incident-type", action="append", default=[])
    search.add_argument("--document-type", action="append", default=[])
    search.add_argument("--include-content", action="store_true")
    search.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate-benchmark", help="validate queries and qrels")
    validate.add_argument("--json", action="store_true")

    benchmark = subparsers.add_parser("benchmark", help="run a frozen retrieval benchmark")
    benchmark.add_argument("--split", choices=("development", "test"), required=True)
    benchmark.add_argument("--confirm-final-test", action="store_true")
    benchmark.add_argument("--json", action="store_true")

    filters = subparsers.add_parser(
        "filter-evaluate", help="run the secondary metadata-filter checks"
    )
    filters.add_argument("--json", action="store_true")
    return parser


def _provider(config: RetrievalConfig, *, force_fake: bool = False):
    if force_fake or os.getenv("AEGIS_RAG_EMBEDDING_PROVIDER", "real") == "fake":
        return FakeEmbeddingProvider(config.embedding_dimension)
    return SentenceTransformerProvider(
        config.model_id,
        revision=config.model_revision,
        device=config.embedding_device,
        batch_size=config.embedding_batch_size,
        expected_dimension=config.embedding_dimension,
    )


def _paths(config: RetrievalConfig):
    return (
        config.evaluation_root / "retrieval_queries_v1.jsonl",
        config.evaluation_root / "retrieval_qrels_v1.jsonl",
    )


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
        return
    for key, item in value.items():
        print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = RetrievalConfig.from_environment()
        queries, qrels = _paths(config)
        force_fake = args.command == "validate-benchmark" or (
            args.command == "search" and args.method == "bm25"
        )
        with connect(config.database_url) as connection:
            repository = RetrievalRepository(connection)
            retriever = HybridRetriever(
                config,
                repository,
                _provider(config, force_fake=force_fake),
            )
            if args.command == "search":
                filters = SearchFilters.validated(
                    services=args.service,
                    incident_types=args.incident_type,
                    document_types=args.document_type,
                )
                result = retriever.search(
                    args.query,
                    method=args.method,
                    top_k=args.top_k,
                    filters=filters,
                    include_content=args.include_content,
                )
            elif args.command == "validate-benchmark":
                benchmark = load_benchmark(queries, qrels)
                validate_qrels(benchmark, retriever.snapshot)
                result = {
                    "valid": True,
                    "queries": len(benchmark.queries),
                    "qrels": len(benchmark.qrels),
                    "corpus_fingerprint": retriever.snapshot.fingerprint,
                    "primary_queries_with_filters": 0,
                }
            elif args.command == "benchmark":
                result = evaluate(
                    retriever,
                    load_benchmark(queries, qrels),
                    split=args.split,
                    output_root=config.runtime_root,
                    confirm_final_test=args.confirm_final_test,
                )
            elif args.command == "filter-evaluate":
                result = evaluate_filter_cases(
                    retriever,
                    config.evaluation_root / "retrieval_filter_cases_v1.jsonl",
                )
            else:
                raise AssertionError(args.command)
        _emit(result, args.json)
        return 0
    except (RetrievalError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
