import pytest
from helpers import artifact

from aegis_rag_evaluation.citation_metrics import (
    gold_citation_metrics,
    structural_citation_validity,
)
from aegis_rag_evaluation.contracts import GoldRecord


@pytest.fixture
def gold() -> GoldRecord:
    return GoldRecord.model_validate(
        {
            "case_id": "toy",
            "expected_status": "grounded",
            "relevant_sections": [
                {
                    "source_path": "runbooks/cpu-saturation.md",
                    "heading_path": ["CPU Saturation Response", "Mitigation"],
                    "grade": 2,
                },
                {
                    "source_path": "runbooks/cpu-saturation.md",
                    "heading_path": ["CPU Saturation Response", "Triage"],
                    "grade": 1,
                },
            ],
            "required_facts": ["A supported factual statement exists."],
            "acceptable_actions": ["A supported response action exists."],
        }
    )


def test_all_correct_citation_precision_and_recall(gold: GoldRecord) -> None:
    citations = [
        {"source_path": section.source_path, "heading_path": section.heading_path}
        for section in gold.relevant_sections
    ]
    result = gold_citation_metrics(citations, gold)
    assert result["precision"] == 1
    assert result["recall"] == 1
    assert result["direct_precision"] == 0.5
    assert result["direct_recall"] == 1


def test_supporting_irrelevant_duplicate_and_empty_citations(gold: GoldRecord) -> None:
    supporting = [
        {
            "source_path": "runbooks/cpu-saturation.md",
            "heading_path": ["CPU Saturation Response", "Triage"],
        }
    ]
    assert gold_citation_metrics(supporting, gold)["direct_precision"] == 0
    irrelevant = [{"source_path": "other.md", "heading_path": ["Other", "Section"]}]
    assert gold_citation_metrics(irrelevant, gold)["precision"] == 0
    duplicate = supporting + supporting
    assert gold_citation_metrics(duplicate, gold)["cited_sections"] == 1
    assert gold_citation_metrics([], gold)["recall"] == 0


def test_structural_duplicate_and_reconstruction_checks() -> None:
    value = artifact()
    assert structural_citation_validity(value)["valid"]
    value["structured_response"]["citations"].append(
        value["structured_response"]["citations"][0]
    )
    result = structural_citation_validity(value)
    assert not result["valid"]
    assert "duplicate_citation" in result["reasons"]
