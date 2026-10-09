from pathlib import Path

import pytest
from helpers import StubRerankingPipeline, grounded_payload, reranked_hit

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.errors import SLMUnavailableError
from aegis_rag_generation.generator import GroundedGenerator
from aegis_rag_generation.provider import FakeSLMProvider


def test_valid_fake_generation_retains_full_lineage(tmp_path: Path) -> None:
    pipeline = StubRerankingPipeline(tmp_path, (reranked_hit(1), reranked_hit(2)))
    generator = GroundedGenerator(
        GenerationConfig(repository=tmp_path, model_path=tmp_path / "model.gguf"),
        pipeline,
        FakeSLMProvider(grounded_payload()),
    )
    outcome = generator.diagnose("Why are database requests failing?")
    assert outcome.response.status == "grounded"
    assert outcome.lineage["corpus_fingerprint"] == "f" * 64
    assert outcome.lineage["prompt_version"] == "grounded_incident_v1"
    assert outcome.lineage["evidence_ids"] == ["E1", "E2"]
    assert len(outcome.lineage["retrieval_and_reranking_results"]) == 2


def test_empty_retrieval_returns_insufficient_without_generation(tmp_path: Path) -> None:
    provider = FakeSLMProvider(grounded_payload())
    outcome = GroundedGenerator(
        GenerationConfig(repository=tmp_path, model_path=tmp_path / "model.gguf"),
        StubRerankingPipeline(tmp_path, ()),
        provider,
    ).diagnose("unrelated query")
    assert outcome.response.status == "insufficient_evidence"
    assert provider.generate_calls == 0


def test_unavailable_slm_fails_explicitly(tmp_path: Path) -> None:
    generator = GroundedGenerator(
        GenerationConfig(repository=tmp_path, model_path=tmp_path / "model.gguf"),
        StubRerankingPipeline(tmp_path, (reranked_hit(1),)),
        FakeSLMProvider(grounded_payload(), unavailable=True),
    )
    with pytest.raises(SLMUnavailableError, match="generation failed"):
        generator.diagnose("query")
