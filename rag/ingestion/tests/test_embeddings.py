import math

import pytest

from aegis_rag_ingestion.embeddings import FakeEmbeddingProvider, validate_vectors
from aegis_rag_ingestion.errors import EmbeddingValidationError


def test_fake_embeddings_are_deterministic_normalized_and_distinct() -> None:
    provider = FakeEmbeddingProvider(16)
    first, repeated, other = provider.embed_documents(["same", "same", "other"])
    assert first == repeated
    assert first != other
    assert len(first) == 16
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_query_instruction_makes_query_embedding_distinct() -> None:
    provider = FakeEmbeddingProvider(8)
    assert provider.embed_query("latency") != provider.embed_documents(["latency"])[0]


def test_vector_contract_rejects_bad_dimension_and_non_finite() -> None:
    with pytest.raises(EmbeddingValidationError, match="dimension"):
        validate_vectors([(1.0,)], 2, normalized=False)
    with pytest.raises(EmbeddingValidationError, match="non-finite"):
        validate_vectors([(float("nan"), 1.0)], 2, normalized=False)
    with pytest.raises(EmbeddingValidationError, match="expected 1"):
        validate_vectors([(1.0, 1.0)], 2, normalized=True)
