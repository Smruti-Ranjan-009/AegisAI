from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aegis_rag_reranking.errors import RerankerConfigurationError

DEFAULT_RERANKER_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"
DEFAULT_RERANKER_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
DEFAULT_RERANKER_FILE = "model.safetensors"
DEFAULT_RERANKER_SHA256 = (
    "821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae"
)
PASSAGE_VERSION = "title-heading-content-v1"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class RerankingConfig:
    repository: Path
    runtime_root: Path
    evaluation_root: Path
    model_cache: Path
    model_id: str = DEFAULT_RERANKER_ID
    model_revision: str = DEFAULT_RERANKER_REVISION
    model_file: str = DEFAULT_RERANKER_FILE
    model_sha256: str = DEFAULT_RERANKER_SHA256
    device: str = "cpu"
    batch_size: int = 16
    candidate_k: int = 10
    evidence_k: int = 5
    passage_version: str = PASSAGE_VERSION
    config_version: int = 1

    def __post_init__(self) -> None:
        if self.candidate_k != 10:
            raise RerankerConfigurationError("Phase 10 rerank candidate_k is frozen at 10")
        if self.evidence_k != 5:
            raise RerankerConfigurationError("Phase 10 generation evidence_k is frozen at 5")
        if self.evidence_k > self.candidate_k:
            raise RerankerConfigurationError("evidence_k cannot exceed candidate_k")
        if self.batch_size <= 0:
            raise RerankerConfigurationError("reranker batch_size must be positive")
        if self.device != "cpu":
            raise RerankerConfigurationError("the default Phase 10 reranker device is CPU")

    @classmethod
    def from_environment(cls, root: Path | None = None) -> RerankingConfig:
        repo = (root or repository_root()).resolve()
        return cls(
            repository=repo,
            runtime_root=Path(
                os.getenv("AEGIS_RAG_RERANKING_RUNTIME_ROOT")
                or repo / ".runtime" / "rag" / "reranking"
            ).resolve(),
            evaluation_root=(repo / "rag" / "evaluation").resolve(),
            model_cache=Path(
                os.getenv("AEGIS_RAG_MODEL_CACHE")
                or repo / ".runtime" / "rag" / "huggingface"
            ).resolve(),
            model_id=os.getenv("AEGIS_RAG_RERANKER_MODEL") or DEFAULT_RERANKER_ID,
            model_revision=(
                os.getenv("AEGIS_RAG_RERANKER_REVISION") or DEFAULT_RERANKER_REVISION
            ),
            device=os.getenv("AEGIS_RAG_RERANKER_DEVICE") or "cpu",
            batch_size=_positive_int("AEGIS_RAG_RERANKER_BATCH_SIZE", 16),
            candidate_k=_positive_int("AEGIS_RAG_RERANK_CANDIDATE_K", 10),
            evidence_k=_positive_int("AEGIS_RAG_GENERATION_EVIDENCE_K", 5),
        )

    def contract(self, retrieval_contract: dict[str, object]) -> dict[str, object]:
        return {
            "config_version": self.config_version,
            "retrieval": retrieval_contract,
            "reranker": {
                "model_id": self.model_id,
                "model_revision": self.model_revision,
                "model_file": self.model_file,
                "model_sha256": self.model_sha256,
                "license": "apache-2.0",
                "device": self.device,
                "candidate_k": self.candidate_k,
                "batch_size": self.batch_size,
                "passage_version": self.passage_version,
                "tie_break": ["rrf_rank", "chunk_id"],
            },
            "generation_evidence_k": self.evidence_k,
            "primary_metric": "ndcg@5",
        }


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RerankerConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RerankerConfigurationError(f"{name} must be positive")
    return value
