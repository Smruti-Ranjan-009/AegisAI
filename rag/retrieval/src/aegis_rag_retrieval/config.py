from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aegis_rag_ingestion.config import DEFAULT_MODEL_ID, DEFAULT_MODEL_REVISION

from aegis_rag_retrieval.errors import ConfigurationError


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class RetrievalConfig:
    repository: Path
    database_url: str
    runtime_root: Path
    evaluation_root: Path
    model_id: str = DEFAULT_MODEL_ID
    model_revision: str = DEFAULT_MODEL_REVISION
    embedding_dimension: int = 384
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    candidate_k: int = 20
    rrf_k: int = 60
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    config_version: int = 1

    @classmethod
    def from_environment(cls, root: Path | None = None) -> RetrievalConfig:
        repo = (root or repository_root()).resolve()
        return cls(
            repository=repo,
            database_url=os.getenv("AEGIS_RAG_DATABASE_URL")
            or "postgresql://aegis:aegis_dev_password@localhost:5432/aegisai",
            runtime_root=Path(
                os.getenv("AEGIS_RAG_RETRIEVAL_RUNTIME_ROOT")
                or repo / ".runtime" / "rag" / "retrieval"
            ).resolve(),
            evaluation_root=(repo / "rag" / "evaluation").resolve(),
            model_id=os.getenv("AEGIS_RAG_EMBEDDING_MODEL") or DEFAULT_MODEL_ID,
            model_revision=os.getenv("AEGIS_RAG_EMBEDDING_REVISION")
            or DEFAULT_MODEL_REVISION,
            embedding_dimension=_positive_int("AEGIS_RAG_EMBEDDING_DIMENSION", 384),
            embedding_device=os.getenv("AEGIS_RAG_EMBEDDING_DEVICE") or "cpu",
            embedding_batch_size=_positive_int("AEGIS_RAG_EMBEDDING_BATCH_SIZE", 32),
            candidate_k=_positive_int("AEGIS_RAG_CANDIDATE_K", 20),
            rrf_k=_positive_int("AEGIS_RAG_RRF_K", 60),
        )

    def retrieval_contract(self) -> dict[str, object]:
        return {
            "config_version": self.config_version,
            "embedding": {
                "dimension": self.embedding_dimension,
                "model_id": self.model_id,
                "model_revision": self.model_revision,
                "normalized": True,
                "query_instruction": "Represent this sentence for searching relevant passages: ",
            },
            "bm25": {"algorithm": "okapi", "b": self.bm25_b, "k1": self.bm25_k1},
            "fusion": {
                "candidate_k": self.candidate_k,
                "method": "reciprocal_rank_fusion",
                "rrf_k": self.rrf_k,
                "weights": {"bm25": 1.0, "dense": 1.0},
            },
        }


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive")
    return value

