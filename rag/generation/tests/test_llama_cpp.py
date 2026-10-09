import hashlib
from pathlib import Path

import pytest

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.errors import ModelIntegrityError
from aegis_rag_generation.llama_cpp import verify_model_file


def test_model_integrity_accepts_exact_local_bytes(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"small fixture")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    config = GenerationConfig(
        repository=tmp_path,
        model_path=model,
        model_sha256=digest,
    )
    result = verify_model_file(config)
    assert result["valid"] is True
    assert result["size_bytes"] == len(b"small fixture")


def test_model_integrity_rejects_wrong_checksum(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"wrong")
    config = GenerationConfig(repository=tmp_path, model_path=model)
    with pytest.raises(ModelIntegrityError, match="checksum mismatch"):
        verify_model_file(config)
