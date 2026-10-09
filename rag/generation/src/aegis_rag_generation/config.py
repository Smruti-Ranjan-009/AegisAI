from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from aegis_rag_generation.errors import GenerationConfigurationError

SLM_REPOSITORY = "Qwen/Qwen3-4B-GGUF"
SLM_REVISION = "bc640142c66e1fdd12af0bd68f40445458f3869b"
SLM_FILENAME = "Qwen3-4B-Q4_K_M.gguf"
SLM_QUANTIZATION = "Q4_K_M"
SLM_SHA256 = "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
SLM_ALIAS = "aegis-qwen3-4b-q4km"
PROMPT_VERSION = "grounded_incident_v1"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def validate_loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise GenerationConfigurationError(
            "llama.cpp endpoint must be a plain loopback HTTP origin"
        )
    if parsed.port is None:
        raise GenerationConfigurationError("llama.cpp endpoint must include a port")
    return value.rstrip("/")


@dataclass(frozen=True)
class GenerationConfig:
    repository: Path
    model_path: Path
    endpoint: str = "http://127.0.0.1:8081"
    model_repository: str = SLM_REPOSITORY
    model_revision: str = SLM_REVISION
    model_filename: str = SLM_FILENAME
    model_sha256: str = SLM_SHA256
    model_alias: str = SLM_ALIAS
    quantization: str = SLM_QUANTIZATION
    prompt_version: str = PROMPT_VERSION
    context_tokens: int = 4096
    max_output_tokens: int = 768
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42
    timeout_seconds: float = 300.0
    config_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", validate_loopback_url(self.endpoint))
        if self.context_tokens != 4096:
            raise GenerationConfigurationError("Phase 10 context is frozen at 4096 tokens")
        if self.max_output_tokens <= 0 or self.max_output_tokens >= self.context_tokens:
            raise GenerationConfigurationError("max output tokens must fit inside context")
        if self.temperature != 0.0 or self.top_p != 1.0 or self.seed != 42:
            raise GenerationConfigurationError("Phase 10 deterministic sampling is frozen")

    @classmethod
    def from_environment(cls, root: Path | None = None) -> GenerationConfig:
        repo = (root or repository_root()).resolve()
        return cls(
            repository=repo,
            model_path=Path(
                os.getenv("AEGIS_RAG_SLM_MODEL_PATH")
                or repo / ".runtime" / "rag" / "models" / SLM_FILENAME
            ).resolve(),
            endpoint=os.getenv("AEGIS_RAG_SLM_ENDPOINT") or "http://127.0.0.1:8081",
            context_tokens=_integer("AEGIS_RAG_SLM_CONTEXT_TOKENS", 4096),
            max_output_tokens=_integer("AEGIS_RAG_SLM_MAX_OUTPUT_TOKENS", 768),
            timeout_seconds=_float("AEGIS_RAG_SLM_TIMEOUT_SECONDS", 300.0),
        )

    def contract(self) -> dict[str, object]:
        return {
            "config_version": self.config_version,
            "model": {
                "repository": self.model_repository,
                "revision": self.model_revision,
                "filename": self.model_filename,
                "sha256": self.model_sha256,
                "quantization": self.quantization,
                "alias": self.model_alias,
            },
            "runtime": {
                "kind": "llama.cpp",
                "endpoint": self.endpoint,
                "context_tokens": self.context_tokens,
                "local_only": True,
            },
            "generation": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "seed": self.seed,
                "max_output_tokens": self.max_output_tokens,
                "thinking": False,
                "retries": 0,
            },
            "prompt_version": self.prompt_version,
        }


def _integer(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise GenerationConfigurationError(f"{name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise GenerationConfigurationError(f"{name} must be numeric") from exc
