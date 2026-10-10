from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.generator import GroundedGenerator
from aegis_rag_generation.llama_cpp import LocalLlamaCppProvider
from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider, SentenceTransformerProvider
from aegis_rag_reranking.cli import build_pipeline
from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_retrieval.config import RetrievalConfig

from aegis_rag_evaluation.artifacts import score_path
from aegis_rag_evaluation.benchmark import load_benchmark, manifest
from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.determinism import run_determinism_check
from aegis_rag_evaluation.errors import EvaluationError
from aegis_rag_evaluation.providers import DebertaNLIProvider, FakeNLIProvider
from aegis_rag_evaluation.reporting import create_reports
from aegis_rag_evaluation.runner import generate_split
from aegis_rag_evaluation.scoring import score_split


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AegisAI Phase 11 offline RAG evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify-nli")
    verify.add_argument("--json", action="store_true")
    generate = commands.add_parser("generate")
    generate.add_argument("--split", choices=("development", "final"), required=True)
    generate.add_argument(
        "--variant", choices=("canonical", "no-reranker-ablation"), required=True
    )
    generate.add_argument("--confirm-final", action="store_true")
    generate.add_argument("--json", action="store_true")
    score = commands.add_parser("score")
    score.add_argument("--split", choices=("development", "final"), required=True)
    score.add_argument(
        "--variant", choices=("canonical", "no-reranker-ablation"), required=True
    )
    score.add_argument("--json", action="store_true")
    report = commands.add_parser("report")
    report.add_argument("--split", choices=("development", "final"), required=True)
    report.add_argument("--json", action="store_true")
    deterministic = commands.add_parser("determinism")
    deterministic.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = None
    try:
        config = EvaluationConfig.from_environment()
        bundle = load_benchmark(config)
        if args.command == "validate":
            result = {"valid": True, **manifest(bundle, config)}
        elif args.command == "verify-nli":
            provider = DebertaNLIProvider(config, local_files_only=True)
            prediction = provider.predict(
                [("A service is unavailable.", "The service is down.")]
            )[0]
            result = {
                "valid": True,
                "model": provider.model_id,
                "revision": provider.model_revision,
                "load_seconds": provider.load_seconds,
                "prediction": prediction.label,
                "probabilities": prediction.probabilities,
            }
        elif args.command in {"generate", "determinism"}:
            context, generator = _generator(config)
            if args.command == "generate":
                result = generate_split(
                    config,
                    bundle,
                    args.split,
                    args.variant,
                    generator,
                    confirm_final=args.confirm_final,
                )
            else:
                result = run_determinism_check(config, bundle, generator)
        elif args.command == "score":
            nli = _nli(config)
            embeddings = _embeddings()
            report = score_split(config, bundle, args.split, args.variant, nli, embeddings)
            result = {
                "benchmark_id": report["benchmark_id"],
                "split": report["split"],
                "variant": report["variant"],
                "metrics": report["metrics"],
                "path": str(score_path(config, bundle, args.split, args.variant)),
            }
        else:
            canonical = _load_score(config, bundle, args.split, "canonical")
            ablation_path = score_path(
                config, bundle, args.split, "no-reranker-ablation"
            )
            ablation = (
                json.loads(ablation_path.read_text(encoding="utf-8"))
                if ablation_path.exists()
                else None
            )
            result = create_reports(config, bundle, args.split, canonical, ablation)
        _emit(result, args.json)
        return 0
    except (EvaluationError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if context is not None:
            context.__exit__(None, None, None)


def _generator(config: EvaluationConfig):
    retrieval = RetrievalConfig.from_environment(config.repository)
    reranking = RerankingConfig.from_environment(config.repository)
    context, pipeline = build_pipeline(retrieval, reranking)
    generation = GenerationConfig.from_environment(config.repository)
    return context, GroundedGenerator(generation, pipeline, LocalLlamaCppProvider(generation))


def _nli(config: EvaluationConfig):
    if os.getenv("AEGIS_RAG_NLI_PROVIDER", "real") == "fake":
        return FakeNLIProvider()
    return DebertaNLIProvider(config, local_files_only=True)


def _embeddings():
    retrieval = RetrievalConfig.from_environment()
    if os.getenv("AEGIS_RAG_EMBEDDING_PROVIDER", "real") == "fake":
        return FakeEmbeddingProvider(retrieval.embedding_dimension)
    return SentenceTransformerProvider(
        retrieval.model_id,
        revision=retrieval.model_revision,
        device=retrieval.embedding_device,
        batch_size=retrieval.embedding_batch_size,
        expected_dimension=retrieval.embedding_dimension,
    )


def _load_score(config, bundle, split, variant):
    path = score_path(config, bundle, split, variant)
    if not path.is_file():
        raise ValueError(f"score artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


if __name__ == "__main__":
    raise SystemExit(main())
