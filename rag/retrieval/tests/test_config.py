from pathlib import Path

import pytest

from aegis_rag_retrieval.config import RetrievalConfig
from aegis_rag_retrieval.errors import ConfigurationError


def test_defaults_are_repository_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AEGIS_RAG_DATABASE_URL",
        "AEGIS_RAG_RETRIEVAL_RUNTIME_ROOT",
        "AEGIS_RAG_CANDIDATE_K",
        "AEGIS_RAG_RRF_K",
    ):
        monkeypatch.delenv(name, raising=False)
    config = RetrievalConfig.from_environment(tmp_path)
    assert config.runtime_root == tmp_path / ".runtime" / "rag" / "retrieval"
    assert config.evaluation_root == tmp_path / "rag" / "evaluation"
    assert config.candidate_k == 20
    assert config.rrf_k == 60


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AEGIS_RAG_CANDIDATE_K", "15")
    monkeypatch.setenv("AEGIS_RAG_RRF_K", "50")
    monkeypatch.setenv("AEGIS_RAG_RETRIEVAL_RUNTIME_ROOT", str(tmp_path / "output"))
    config = RetrievalConfig.from_environment(tmp_path)
    assert config.candidate_k == 15
    assert config.rrf_k == 50
    assert config.runtime_root == (tmp_path / "output").resolve()
    monkeypatch.setenv("AEGIS_RAG_CANDIDATE_K", "0")
    with pytest.raises(ConfigurationError, match="positive"):
        RetrievalConfig.from_environment(tmp_path)

