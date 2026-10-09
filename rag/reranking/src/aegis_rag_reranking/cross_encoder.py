from __future__ import annotations

import hashlib
import math
from pathlib import Path
from time import perf_counter
from typing import Any

from aegis_rag_reranking.config import RerankingConfig
from aegis_rag_reranking.errors import RerankerProviderError


class CrossEncoderProvider:
    """Pinned safetensors-only SentenceTransformers cross-encoder adapter."""

    def __init__(self, config: RerankingConfig, *, local_files_only: bool = False) -> None:
        try:
            from huggingface_hub import hf_hub_download
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RerankerProviderError(
                "real reranking requires: pip install -e 'rag/reranking[models]'"
            ) from exc
        config.model_cache.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        try:
            weight_path = Path(
                hf_hub_download(
                    repo_id=config.model_id,
                    filename=config.model_file,
                    revision=config.model_revision,
                    cache_dir=config.model_cache,
                    local_files_only=local_files_only,
                )
            )
            actual = _sha256(weight_path)
            if actual != config.model_sha256:
                raise RerankerProviderError(
                    f"reranker checksum mismatch: expected {config.model_sha256}, got {actual}"
                )
            self._model: Any = CrossEncoder(
                config.model_id,
                revision=config.model_revision,
                device=config.device,
                cache_folder=str(config.model_cache),
                local_files_only=local_files_only,
                trust_remote_code=False,
                model_kwargs={"use_safetensors": True},
            )
        except RerankerProviderError:
            raise
        except Exception as exc:
            raise RerankerProviderError(f"unable to load pinned reranker: {exc}") from exc
        self._model_id = config.model_id
        self._model_revision = config.model_revision
        self._batch_size = config.batch_size
        self._load_seconds = perf_counter() - started

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_revision(self) -> str:
        return self._model_revision

    @property
    def load_seconds(self) -> float:
        return self._load_seconds

    def score(self, query: str, passages: list[str]) -> tuple[float, ...]:
        if not passages:
            return ()
        try:
            raw = self._model.predict(
                [(query, passage) for passage in passages],
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            values = tuple(float(value) for value in raw.reshape(-1))
        except Exception as exc:
            raise RerankerProviderError(f"cross-encoder scoring failed: {exc}") from exc
        if len(values) != len(passages) or any(not math.isfinite(value) for value in values):
            raise RerankerProviderError("cross-encoder returned an invalid score vector")
        return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
