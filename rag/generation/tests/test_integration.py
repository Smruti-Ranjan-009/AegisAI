from pathlib import Path

import pytest
from helpers import StubRerankingPipeline, grounded_payload, reranked_hit

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.generator import GroundedGenerator
from aegis_rag_generation.provider import FakeSLMProvider

pytestmark = pytest.mark.integration


def test_reranked_evidence_to_validated_grounded_result(tmp_path: Path) -> None:
    results = tuple(reranked_hit(index) for index in range(1, 6))
    provider = FakeSLMProvider(grounded_payload())
    outcome = GroundedGenerator(
        GenerationConfig(repository=tmp_path, model_path=tmp_path / "model.gguf"),
        StubRerankingPipeline(tmp_path, results),
        provider,
    ).diagnose("What caused the retry pressure and what should we do?")
    assert outcome.response.status == "grounded"
    assert [item.evidence_id for item in outcome.evidence] == [
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
    ]
    assert {item.evidence_id for item in outcome.response.citations} == {"E1", "E2"}
    assert "<USER_QUERY>" in provider.last_user_prompt
    assert "<EVIDENCE>" in provider.last_user_prompt
