from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aegis_rag_ingestion.errors import ConfigurationError

DEFAULT_MODEL_ID = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class IngestionConfig:
    repository: Path
    corpus_root: Path
    runtime_root: Path
    database_url: str
    model_id: str = DEFAULT_MODEL_ID
    model_revision: str = DEFAULT_MODEL_REVISION
    embedding_dimension: int = 384
    target_tokens: int = 400
    overlap_tokens: int = 60
    minimum_chunk_tokens: int = 8
    batch_size: int = 32
    device: str = "cpu"
    chunk_schema_version: int = 1

    @classmethod
    def from_environment(cls, root: Path | None = None) -> IngestionConfig:
        repo = (root or repository_root()).resolve()
        corpus = Path(os.getenv("AEGIS_RAG_CORPUS_ROOT") or repo / "rag" / "knowledge")
        runtime = Path(os.getenv("AEGIS_RAG_RUNTIME_ROOT") or repo / ".runtime" / "rag")
        database_url = os.getenv("AEGIS_RAG_DATABASE_URL") or (
            "postgresql://aegis:aegis_dev_password@localhost:5432/aegisai"
        )
        target = _positive_int("AEGIS_RAG_TARGET_TOKENS", 400)
        overlap = _nonnegative_int("AEGIS_RAG_OVERLAP_TOKENS", 60)
        if overlap >= target:
            raise ConfigurationError("AEGIS_RAG_OVERLAP_TOKENS must be below target tokens")
        return cls(
            repository=repo,
            corpus_root=corpus.resolve(),
            runtime_root=runtime.resolve(),
            database_url=database_url,
            model_id=os.getenv("AEGIS_RAG_EMBEDDING_MODEL") or DEFAULT_MODEL_ID,
            model_revision=os.getenv("AEGIS_RAG_EMBEDDING_REVISION") or DEFAULT_MODEL_REVISION,
            embedding_dimension=_positive_int("AEGIS_RAG_EMBEDDING_DIMENSION", 384),
            target_tokens=target,
            overlap_tokens=overlap,
            minimum_chunk_tokens=_positive_int("AEGIS_RAG_MINIMUM_CHUNK_TOKENS", 8),
            batch_size=_positive_int("AEGIS_RAG_EMBEDDING_BATCH_SIZE", 32),
            device=os.getenv("AEGIS_RAG_EMBEDDING_DEVICE") or "cpu",
        )


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 0:
        raise ConfigurationError(f"{name} must not be negative")
    return value
