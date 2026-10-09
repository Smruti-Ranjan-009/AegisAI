from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from aegis_rag_reranking.cli import build_pipeline
from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.errors import RerankingError
from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.contracts import SearchFilters

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.errors import GenerationError
from aegis_rag_generation.generator import GroundedGenerator
from aegis_rag_generation.llama_cpp import LocalLlamaCppProvider, verify_model_file
from aegis_rag_generation.provider import FakeSLMProvider
from aegis_rag_generation.smoke import run_real_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AegisAI local grounded generation")
    commands = parser.add_subparsers(dest="command", required=True)
    diagnose = commands.add_parser("diagnose")
    diagnose.add_argument("--query", required=True)
    diagnose.add_argument("--service", action="append", default=[])
    diagnose.add_argument("--incident-type", action="append", default=[])
    diagnose.add_argument("--document-type", action="append", default=[])
    diagnose.add_argument("--json", action="store_true")
    health = commands.add_parser("model-health")
    health.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify-model")
    verify.add_argument("--json", action="store_true")
    smoke = commands.add_parser("smoke")
    smoke.add_argument("--json", action="store_true")
    return parser


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
        return
    for key, item in value.items():
        print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = None
    try:
        config = GenerationConfig.from_environment()
        if args.command == "verify-model":
            result = verify_model_file(config)
        else:
            provider = LocalLlamaCppProvider(config)
            if args.command == "model-health":
                result = provider.health()
            else:
                retrieval = RetrievalConfig.from_environment()
                reranking = RerankingConfig.from_environment()
                context, pipeline = build_pipeline(retrieval, reranking)
                if os.getenv("AEGIS_RAG_SLM_PROVIDER", "real") == "fake":
                    fake = {
                        "status": "insufficient_evidence",
                        "summary": "Fake provider has no configured diagnosis.",
                        "suspected_causes": [],
                        "recommended_actions": [],
                        "citations": [],
                    }
                    selected_provider: Any = FakeSLMProvider(fake)
                else:
                    selected_provider = provider
                generator = GroundedGenerator(config, pipeline, selected_provider)
                if args.command == "smoke":
                    result = run_real_smoke(
                        generator,
                        config.repository
                        / ".runtime"
                        / "rag"
                        / "generation"
                        / "real-smoke-report.json",
                    )
                else:
                    filters = SearchFilters.validated(
                        services=args.service,
                        incident_types=args.incident_type,
                        document_types=args.document_type,
                    )
                    result = generator.diagnose(args.query, filters=filters).to_dict()
        _emit(result, args.json)
        return 0
    except (GenerationError, RerankingError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if context is not None:
            context.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
