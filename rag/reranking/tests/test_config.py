from pathlib import Path

import pytest

from aegis_rag_reranking.config import (
    DEFAULT_RERANKER_REVISION,
    RerankingConfig,
)
from aegis_rag_reranking.errors import RerankerConfigurationError


def test_defaults_are_frozen_and_repo_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "AEGIS_RAG_RERANKING_RUNTIME_ROOT",
        "AEGIS_RAG_MODEL_CACHE",
        "AEGIS_RAG_RERANKER_MODEL",
        "AEGIS_RAG_RERANKER_REVISION",
        "AEGIS_RAG_RERANKER_DEVICE",
        "AEGIS_RAG_RERANK_CANDIDATE_K",
        "AEGIS_RAG_GENERATION_EVIDENCE_K",
    ):
        monkeypatch.delenv(name, raising=False)
    config = RerankingConfig.from_environment(tmp_path)
    assert config.runtime_root == tmp_path / ".runtime" / "rag" / "reranking"
    assert config.model_cache == tmp_path / ".runtime" / "rag" / "huggingface"
    assert config.model_revision == DEFAULT_RERANKER_REVISION
    assert config.candidate_k == 10
    assert config.evidence_k == 5
    assert config.device == "cpu"


@pytest.mark.parametrize("candidate,evidence", [(9, 5), (10, 4), (10, 11)])
def test_frozen_depths_reject_drift(tmp_path: Path, candidate: int, evidence: int) -> None:
    with pytest.raises(RerankerConfigurationError):
        RerankingConfig(
            repository=tmp_path,
            runtime_root=tmp_path,
            evaluation_root=tmp_path,
            model_cache=tmp_path,
            candidate_k=candidate,
            evidence_k=evidence,
        )
