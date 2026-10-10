from helpers import artifact

from aegis_rag_evaluation.completeness import evaluate_completeness
from aegis_rag_evaluation.contracts import GoldRecord
from aegis_rag_evaluation.providers import FakeNLIProvider


def gold(status: str = "grounded") -> GoldRecord:
    return GoldRecord.model_validate(
        {
            "case_id": "toy",
            "expected_status": status,
            "relevant_sections": [] if status != "grounded" else [
                {
                    "source_path": "runbooks/cpu-saturation.md",
                    "heading_path": ["CPU Saturation Response", "Mitigation"],
                    "grade": 2,
                }
            ],
            "required_facts": []
            if status != "grounded"
            else ["Fact one exists.", "Fact two exists."],
            "acceptable_actions": [] if status != "grounded" else ["Action one is supported."],
        }
    )


def test_all_partial_and_zero_fact_coverage() -> None:
    all_result = evaluate_completeness(
        artifact(), gold(), FakeNLIProvider(["entailment", "entailment", "entailment"])
    )
    assert all_result["nli_expected_fact_coverage"] == 1
    partial = evaluate_completeness(
        artifact(), gold(), FakeNLIProvider(["entailment", "neutral", "entailment"])
    )
    assert partial["nli_expected_fact_coverage"] == 0.5
    zero = evaluate_completeness(
        artifact(), gold(), FakeNLIProvider(["neutral", "contradiction", "neutral"])
    )
    assert zero["nli_expected_fact_coverage"] == 0


def test_duplicate_generated_claims_do_not_change_gold_denominator() -> None:
    value = artifact()
    value["structured_response"]["suspected_causes"].append(
        value["structured_response"]["suspected_causes"][0]
    )
    result = evaluate_completeness(value, gold(), FakeNLIProvider())
    assert result["fact_count"] == 2


def test_empty_grounded_answer_can_score_zero_and_insufficient_is_excluded() -> None:
    empty = artifact()
    empty["structured_response"]["summary"] = "No details."
    empty["structured_response"]["suspected_causes"] = []
    empty["structured_response"]["recommended_actions"] = []
    result = evaluate_completeness(
        empty, gold(), FakeNLIProvider(["neutral", "neutral", "neutral"])
    )
    assert result["nli_expected_fact_coverage"] == 0
    excluded = evaluate_completeness(
        artifact("insufficient_evidence"), gold("insufficient_evidence"), FakeNLIProvider()
    )
    assert excluded["excluded"] is True
