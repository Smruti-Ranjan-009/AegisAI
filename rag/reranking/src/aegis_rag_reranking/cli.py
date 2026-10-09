from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from aegis_rag_ingestion.database import connect
from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider, SentenceTransformerProvider
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import SearchFilters
from aegis_rag_retrieval.repository import RetrievalRepository
from aegis_rag_retrieval.retriever import HybridRetriever

from aegis_rag_reranking.benchmark import load_benchmark, validate_qrels
from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.cross_encoder import CrossEncoderProvider
from aegis_rag_reranking.errors import RerankingError
from aegis_rag_reranking.evaluation import evaluate
from aegis_rag_reranking.provider import FakeRerankerProvider
from aegis_rag_reranking.reranker import RerankingPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AegisAI offline cross-encoder reranking")
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--service", action="append", default=[])
    search.add_argument("--incident-type", action="append", default=[])
    search.add_argument("--document-type", action="append", default=[])
    search.add_argument("--include-content", action="store_true")
    search.add_argument("--json", action="store_true")
    validate = commands.add_parser("validate-benchmark")
    validate.add_argument("--json", action="store_true")
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--split", choices=("development", "final"), required=True)
    benchmark.add_argument("--confirm-final", action="store_true")
    benchmark.add_argument("--json", action="store_true")
    return parser


def build_pipeline(
    retrieval: RetrievalConfig,
    reranking: RerankingConfig,
    *,
    fake_reranker: bool = False,
) -> tuple[Any, RerankingPipeline]:
    connection_context = connect(retrieval.database_url)
    connection = connection_context.__enter__()
    if os.getenv("AEGIS_RAG_EMBEDDING_PROVIDER", "real") == "fake":
        embeddings = FakeEmbeddingProvider(retrieval.embedding_dimension)
    else:
        embeddings = SentenceTransformerProvider(
            retrieval.model_id,
            revision=retrieval.model_revision,
            device=retrieval.embedding_device,
            batch_size=retrieval.embedding_batch_size,
            expected_dimension=retrieval.embedding_dimension,
        )
    retriever = HybridRetriever(retrieval, RetrievalRepository(connection), embeddings)
    use_fake = fake_reranker or os.getenv("AEGIS_RAG_RERANKER_PROVIDER", "real") == "fake"
    provider = FakeRerankerProvider() if use_fake else CrossEncoderProvider(reranking)
    return connection_context, RerankingPipeline(reranking, retriever, provider)


def _paths(config: RerankingConfig):
    return (
        config.evaluation_root / "reranking_queries_v1.jsonl",
        config.evaluation_root / "reranking_qrels_v1.jsonl",
    )


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = None
    try:
        retrieval = RetrievalConfig.from_environment()
        reranking = RerankingConfig.from_environment()
        context, pipeline = build_pipeline(
            retrieval,
            reranking,
            fake_reranker=args.command == "validate-benchmark",
        )
        queries, qrels = _paths(reranking)
        if args.command == "search":
            filters = SearchFilters.validated(
                services=args.service,
                incident_types=args.incident_type,
                document_types=args.document_type,
            )
            result = pipeline.search(
                args.query,
                top_k=args.top_k,
                filters=filters,
                include_content=args.include_content,
            )
        elif args.command == "validate-benchmark":
            benchmark = load_benchmark(queries, qrels)
            validate_qrels(benchmark, pipeline.retriever.snapshot)
            result = {
                "valid": True,
                "queries": len(benchmark.queries),
                "qrels": len(benchmark.qrels),
                "development": len(benchmark.selected("development")),
                "final": len(benchmark.selected("final")),
                "query_hash": benchmark.query_hash,
                "qrel_hash": benchmark.qrel_hash,
                "corpus_fingerprint": pipeline.retriever.snapshot.fingerprint,
            }
        else:
            result = evaluate(
                pipeline,
                load_benchmark(queries, qrels),
                split=args.split,
                output_root=reranking.runtime_root,
                confirm_final=args.confirm_final,
            )
        _emit(result, args.json)
        return 0
    except (RerankingError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if context is not None:
            context.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
