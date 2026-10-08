from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

from aegis_rag_ingestion.chunking import chunk_corpus
from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.database import connect
from aegis_rag_ingestion.embeddings import (
    FakeEmbeddingProvider,
    SentenceTransformerProvider,
    validate_vectors,
)
from aegis_rag_ingestion.errors import IngestionError
from aegis_rag_ingestion.ingestion import ingest, inspect_corpus
from aegis_rag_ingestion.parsing import discover_documents
from aegis_rag_ingestion.repository import KnowledgeRepository
from aegis_rag_ingestion.tokenization import DeterministicTokenizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AegisAI knowledge ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("inspect", "validate and summarize the corpus without a model or database"),
        ("migrate", "upgrade the Python-owned rag schema"),
        ("ingest", "embed and atomically persist the corpus"),
        ("validate", "validate persisted vectors and optional exact distance query"),
        ("status", "show knowledge-store counts and the latest ingestion run"),
        ("embed-validate", "load the real model and validate its vector contract"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--json", action="store_true", help="emit machine-readable JSON")
        if name == "validate":
            child.add_argument("--smoke-query")
    return parser


def _provider(config: IngestionConfig):
    if os.getenv("AEGIS_RAG_EMBEDDING_PROVIDER", "real") == "fake":
        return FakeEmbeddingProvider(config.embedding_dimension)
    return SentenceTransformerProvider(
        config.model_id,
        revision=config.model_revision,
        device=config.device,
        batch_size=config.batch_size,
        expected_dimension=config.embedding_dimension,
    )


def _inspect(config: IngestionConfig) -> dict[str, Any]:
    class InspectProvider:
        model_id = "none"
        model_revision = "none"
        dimension = config.embedding_dimension
        normalized = True
        tokenizer = DeterministicTokenizer()

    result = inspect_corpus(config, InspectProvider())  # type: ignore[arg-type]
    result["note"] = "token counts use the dependency-light inspection tokenizer"
    return result


def _migrate(config: IngestionConfig) -> dict[str, Any]:
    package_root = Path(__file__).resolve().parents[2]
    alembic = Config(str(package_root / "alembic.ini"))
    alembic.set_main_option("script_location", str(package_root / "migrations"))
    alembic.set_main_option(
        "sqlalchemy.url",
        config.database_url.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    command.upgrade(alembic, "head")
    return {"status": "migrated", "revision": "head"}


def _validate(config: IngestionConfig, query: str | None) -> dict[str, Any]:
    with connect(config.database_url) as connection:
        repository = KnowledgeRepository(connection)
        result = repository.validate_store(config.embedding_dimension)
        if query:
            provider = _provider(config)
            vector = provider.embed_query(query)
            validate_vectors([vector], config.embedding_dimension, normalized=True)
            result["smoke_query"] = query
            result["matches"] = repository.exact_smoke_query(vector)
    return result


def _status(config: IngestionConfig) -> dict[str, Any]:
    with connect(config.database_url) as connection:
        return KnowledgeRepository(connection).status()


def _embed_validate(config: IngestionConfig) -> dict[str, Any]:
    provider = _provider(config)
    documents = discover_documents(config.corpus_root)
    chunks = chunk_corpus(
        documents[:1],
        provider.tokenizer,
        target_tokens=config.target_tokens,
        overlap_tokens=config.overlap_tokens,
        minimum_tokens=config.minimum_chunk_tokens,
    )
    vectors = provider.embed_documents([chunks[0].embedded_text])
    query = provider.embed_query("diagnose elevated service latency")
    validate_vectors([*vectors, query], config.embedding_dimension, normalized=True)
    return {
        "model_id": provider.model_id,
        "model_revision": provider.model_revision,
        "dimension": provider.dimension,
        "normalized": provider.normalized,
        "tokenizer": provider.tokenizer.identity,
        "sample_document_tokens": chunks[0].token_count,
    }


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
        return
    for key, item in value.items():
        print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = IngestionConfig.from_environment()
        match args.command:
            case "inspect":
                result = _inspect(config)
            case "migrate":
                result = _migrate(config)
            case "ingest":
                result = ingest(config, _provider(config))
            case "validate":
                result = _validate(config, args.smoke_query)
            case "status":
                result = _status(config)
            case "embed-validate":
                result = _embed_validate(config)
            case _:
                raise AssertionError(args.command)
        _emit(result, args.json)
        return 0 if result.get("valid", True) else 2
    except (IngestionError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
