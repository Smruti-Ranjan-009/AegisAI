from pathlib import Path

import pytest

from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.errors import ConfigurationError

PATH_VARIABLES = (
    "AEGIS_RAG_CORPUS_ROOT",
    "AEGIS_RAG_RUNTIME_ROOT",
    "AEGIS_RAG_DATABASE_URL",
    "AEGIS_RAG_EMBEDDING_MODEL",
    "AEGIS_RAG_EMBEDDING_REVISION",
    "AEGIS_RAG_EMBEDDING_DIMENSION",
    "AEGIS_RAG_TARGET_TOKENS",
    "AEGIS_RAG_OVERLAP_TOKENS",
    "AEGIS_RAG_MINIMUM_CHUNK_TOKENS",
    "AEGIS_RAG_EMBEDDING_BATCH_SIZE",
    "AEGIS_RAG_EMBEDDING_DEVICE",
)


def test_defaults_are_repository_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    config = IngestionConfig.from_environment(tmp_path)

    assert config.corpus_root == tmp_path / "rag" / "knowledge"
    assert config.runtime_root == tmp_path / ".runtime" / "rag"
    assert config.embedding_dimension == 384
    assert (config.target_tokens, config.overlap_tokens) == (400, 60)


def test_environment_overrides_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGIS_RAG_CORPUS_ROOT", str(tmp_path / "corpus"))
    monkeypatch.setenv("AEGIS_RAG_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("AEGIS_RAG_DATABASE_URL", "postgresql://test/test")
    monkeypatch.setenv("AEGIS_RAG_TARGET_TOKENS", "120")
    monkeypatch.setenv("AEGIS_RAG_OVERLAP_TOKENS", "20")

    config = IngestionConfig.from_environment(tmp_path)

    assert config.corpus_root == tmp_path / "corpus"
    assert config.runtime_root == tmp_path / "runtime"
    assert config.database_url == "postgresql://test/test"
    assert (config.target_tokens, config.overlap_tokens) == (120, 20)


def test_blank_optional_paths_retain_safe_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGIS_RAG_CORPUS_ROOT", "")
    monkeypatch.setenv("AEGIS_RAG_RUNTIME_ROOT", "")
    config = IngestionConfig.from_environment(tmp_path)
    assert config.corpus_root == tmp_path / "rag" / "knowledge"
    assert config.runtime_root == tmp_path / ".runtime" / "rag"


def test_overlap_must_be_below_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGIS_RAG_TARGET_TOKENS", "20")
    monkeypatch.setenv("AEGIS_RAG_OVERLAP_TOKENS", "20")
    with pytest.raises(ConfigurationError, match="below target"):
        IngestionConfig.from_environment(tmp_path)
