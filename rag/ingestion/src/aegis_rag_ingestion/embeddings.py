from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from typing import Any

import numpy as np

from aegis_rag_ingestion.contracts import Tokenizer
from aegis_rag_ingestion.errors import EmbeddingValidationError
from aegis_rag_ingestion.tokenization import DeterministicTokenizer

QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class FakeEmbeddingProvider:
    """Deterministic normalized embeddings for unit tests and hosted CI."""

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension
        self._tokenizer = DeterministicTokenizer()

    @property
    def model_id(self) -> str:
        return "aegis-fake-embedding-v1"

    @property
    def model_revision(self) -> str:
        return "deterministic-v1"

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return True

    @property
    def tokenizer(self) -> Tokenizer:
        return self._tokenizer

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(QUERY_INSTRUCTION + text)

    def _embed(self, text: str) -> tuple[float, ...]:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            values.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        vector = np.asarray(values[: self.dimension], dtype=np.float64)
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0
        return tuple(float(value) for value in vector / norm)


class SentenceTransformerProvider:
    """Lazy adapter for the local BGE embedding model and tokenizer."""

    def __init__(
        self,
        model_id: str,
        *,
        revision: str,
        device: str = "cpu",
        batch_size: int = 32,
        expected_dimension: int = 384,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingValidationError(
                "real embeddings require: pip install -e 'rag/ingestion[embeddings]'"
            ) from exc
        self._model: Any = SentenceTransformer(model_id, revision=revision, device=device)
        self._model_id = model_id
        self._model_revision = revision
        self._batch_size = batch_size
        self._dimension = int(self._model.get_embedding_dimension())
        if self._dimension != expected_dimension:
            raise EmbeddingValidationError(
                f"model dimension {self._dimension} does not match expected {expected_dimension}"
            )
        self._tokenizer = HuggingFaceTokenizer(self._model.tokenizer, model_id)

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_revision(self) -> str:
        return self._model_revision

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return True

    @property
    def tokenizer(self) -> Tokenizer:
        return self._tokenizer

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._encode([QUERY_INSTRUCTION + text])[0]

    def _encode(self, texts: list[str]) -> list[tuple[float, ...]]:
        encoded = self._model.encode(
            texts,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = [tuple(float(value) for value in row) for row in encoded]
        validate_vectors(vectors, self.dimension, normalized=True)
        return vectors


class HuggingFaceTokenizer:
    def __init__(self, tokenizer: Any, model_id: str) -> None:
        self._tokenizer = tokenizer
        self._identity = model_id

    @property
    def identity(self) -> str:
        return self._identity

    def encode(self, text: str) -> list[int]:
        return list(self._tokenizer.encode(text, add_special_tokens=False))

    def decode(self, token_ids: list[int]) -> str:
        return str(
            self._tokenizer.decode(
                token_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )
        ).strip()


def validate_vectors(
    vectors: Iterable[tuple[float, ...]], dimension: int, *, normalized: bool
) -> None:
    for index, vector in enumerate(vectors):
        if len(vector) != dimension:
            raise EmbeddingValidationError(
                f"embedding {index} has dimension {len(vector)}; expected {dimension}"
            )
        if any(not math.isfinite(value) for value in vector):
            raise EmbeddingValidationError(f"embedding {index} contains a non-finite value")
        norm = math.sqrt(sum(value * value for value in vector))
        if normalized and not math.isclose(norm, 1.0, abs_tol=1e-5):
            raise EmbeddingValidationError(f"embedding {index} has norm {norm:.8f}; expected 1")
