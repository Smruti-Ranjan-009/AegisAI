import pytest
from helpers import artifact

from aegis_rag_evaluation.claim_support import evaluate_claim_support
from aegis_rag_evaluation.errors import EvaluatorUnavailableError
from aegis_rag_evaluation.providers import FakeNLIProvider


def test_entailment_contradiction_neutral_and_summary_are_distinct() -> None:
    provider = FakeNLIProvider(["entailment", "contradiction", "neutral"])
    result = evaluate_claim_support(artifact(), provider)
    assert result["supported_claims"] == 1
    assert result["contradicted_claims"] == 1
    assert result["neutral_claims"] == 0
    assert result["summary_support_proxy"]["label"] == "neutral"
    assert provider.pairs_scored == 3
    assert provider.inference_seconds >= 0


def test_multi_evidence_is_concatenated_in_declared_order() -> None:
    value = artifact()
    value["evidence"].append(
        {
            "evidence_id": "E2",
            "source_path": "runbooks/cpu-saturation.md",
            "heading_path": ["CPU Saturation Response", "Triage"],
            "content": "SECOND EVIDENCE",
        }
    )
    value["structured_response"]["recommended_actions"][0]["evidence"] = ["E2", "E1"]
    value["structured_response"]["citations"].append(
        {
            "evidence_id": "E2",
            "source_path": "runbooks/cpu-saturation.md",
            "heading_path": ["CPU Saturation Response", "Triage"],
        }
    )
    provider = FakeNLIProvider()
    evaluate_claim_support(value, provider)
    assert provider.pairs[1][0].startswith("SECOND EVIDENCE")


def test_zero_claims_have_no_invented_rate() -> None:
    result = evaluate_claim_support(artifact("insufficient_evidence"), FakeNLIProvider())
    assert result["claim_count"] == 0
    assert result["nli_supported_claim_rate"] is None


def test_malformed_evaluator_label_fails() -> None:
    with pytest.raises(EvaluatorUnavailableError, match="invalid label"):
        evaluate_claim_support(artifact(), FakeNLIProvider(["maybe"]))
