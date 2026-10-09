import json

import pytest
from helpers import grounded_payload, reranked_hit

from aegis_rag_generation.citations import parse_and_validate
from aegis_rag_generation.errors import GenerationValidationError
from aegis_rag_generation.evidence import build_evidence_pack


@pytest.fixture
def evidence():
    return build_evidence_pack((reranked_hit(1), reranked_hit(2)))


def test_valid_grounded_response_reconstructs_metadata(evidence) -> None:
    result = parse_and_validate(json.dumps(grounded_payload()), evidence)
    assert result.status == "grounded"
    assert result.citations[0].source_path == "runbooks/source-1.md"
    assert result.citations[0].heading_path == ["Source 1", "Triage"]


def test_valid_insufficient_evidence_response(evidence) -> None:
    raw = {
        "status": "insufficient_evidence",
        "summary": "The supplied evidence does not address this topic.",
        "suspected_causes": [],
        "recommended_actions": [],
        "citations": [],
    }
    assert parse_and_validate(json.dumps(raw), evidence).status == "insufficient_evidence"


def test_malformed_json_fails_closed(evidence) -> None:
    with pytest.raises(GenerationValidationError, match="invalid JSON/schema"):
        parse_and_validate("not json", evidence)


def test_unknown_citation_fails_closed(evidence) -> None:
    raw = grounded_payload()
    raw["citations"][1]["evidence_id"] = "E3"
    with pytest.raises(GenerationValidationError, match="unknown evidence"):
        parse_and_validate(json.dumps(raw), evidence)


def test_missing_citation_fails_closed(evidence) -> None:
    raw = grounded_payload()
    raw["citations"] = [{"evidence_id": "E1"}]
    with pytest.raises(GenerationValidationError, match="exactly cover"):
        parse_and_validate(json.dumps(raw), evidence)


def test_duplicate_citation_fails_closed(evidence) -> None:
    raw = grounded_payload()
    raw["citations"].append({"evidence_id": "E1"})
    with pytest.raises(GenerationValidationError, match="duplicate"):
        parse_and_validate(json.dumps(raw), evidence)


def test_wrong_status_fails_schema_validation(evidence) -> None:
    raw = grounded_payload()
    raw["status"] = "confident"
    with pytest.raises(GenerationValidationError, match="invalid JSON/schema"):
        parse_and_validate(json.dumps(raw), evidence)


def test_insufficient_status_cannot_smuggle_grounded_claims(evidence) -> None:
    raw = grounded_payload()
    raw["status"] = "insufficient_evidence"
    with pytest.raises(GenerationValidationError, match="must not contain claims"):
        parse_and_validate(json.dumps(raw), evidence)
