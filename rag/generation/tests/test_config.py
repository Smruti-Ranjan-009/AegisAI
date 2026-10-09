from pathlib import Path

import pytest

from aegis_rag_generation.config import SLM_FILENAME, GenerationConfig
from aegis_rag_generation.errors import GenerationConfigurationError


def test_defaults_are_repo_local_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "AEGIS_RAG_SLM_MODEL_PATH",
        "AEGIS_RAG_SLM_ENDPOINT",
        "AEGIS_RAG_SLM_CONTEXT_TOKENS",
        "AEGIS_RAG_SLM_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    config = GenerationConfig.from_environment(tmp_path)
    assert config.model_path == tmp_path / ".runtime" / "rag" / "models" / SLM_FILENAME
    assert config.endpoint == "http://127.0.0.1:8081"
    assert config.context_tokens == 4096
    assert config.temperature == 0
    assert config.top_p == 1
    assert config.seed == 42


@pytest.mark.parametrize(
    "url",
    (
        "https://127.0.0.1:8081",
        "http://example.com:8081",
        "http://127.0.0.1:8081/path",
        "http://user@localhost:8081",
        "http://localhost",
    ),
)
def test_non_loopback_or_ambiguous_endpoints_are_rejected(tmp_path: Path, url: str) -> None:
    with pytest.raises(GenerationConfigurationError):
        GenerationConfig(repository=tmp_path, model_path=tmp_path / "model.gguf", endpoint=url)
