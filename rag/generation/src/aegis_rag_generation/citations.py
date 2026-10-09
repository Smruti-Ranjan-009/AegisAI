from __future__ import annotations

from pydantic import ValidationError

from aegis_rag_generation.contracts import EvidenceItem
from aegis_rag_generation.errors import GenerationValidationError
from aegis_rag_generation.schema import Citation, GroundedResponse, RawGroundedResponse


def parse_and_validate(text: str, evidence: tuple[EvidenceItem, ...]) -> GroundedResponse:
    try:
        raw = RawGroundedResponse.model_validate_json(text)
    except ValidationError as exc:
        raise GenerationValidationError(
            "generation_validation_failed: invalid JSON/schema"
        ) from exc

    evidence_map = {item.evidence_id: item for item in evidence}
    claim_ids = [
        evidence_id
        for claim in (*raw.suspected_causes, *raw.recommended_actions)
        for evidence_id in claim.evidence
    ]
    citation_ids = [citation.evidence_id for citation in raw.citations]
    if raw.status == "insufficient_evidence":
        if raw.suspected_causes or raw.recommended_actions or raw.citations:
            raise GenerationValidationError(
                "generation_validation_failed: insufficient evidence must not contain claims"
            )
        return GroundedResponse(
            status=raw.status,
            summary=raw.summary,
            suspected_causes=[],
            recommended_actions=[],
            citations=[],
        )
    if not raw.suspected_causes or not raw.recommended_actions:
        raise GenerationValidationError(
            "generation_validation_failed: grounded output requires causes and actions"
        )
    if any(not claim.evidence for claim in (*raw.suspected_causes, *raw.recommended_actions)):
        raise GenerationValidationError(
            "generation_validation_failed: every grounded claim requires evidence"
        )
    unknown = sorted((set(claim_ids) | set(citation_ids)) - set(evidence_map))
    if unknown:
        raise GenerationValidationError(
            f"generation_validation_failed: unknown evidence IDs {unknown}"
        )
    if len(citation_ids) != len(set(citation_ids)):
        raise GenerationValidationError(
            "generation_validation_failed: duplicate citation ID"
        )
    if set(citation_ids) != set(claim_ids) or not citation_ids:
        raise GenerationValidationError(
            "generation_validation_failed: citations must exactly cover claim evidence"
        )
    citations = [
        Citation(
            evidence_id=evidence_id,
            source_path=evidence_map[evidence_id].source_path,
            heading_path=list(evidence_map[evidence_id].heading_path),
        )
        for evidence_id in citation_ids
    ]
    return GroundedResponse(
        status=raw.status,
        summary=raw.summary,
        suspected_causes=raw.suspected_causes,
        recommended_actions=raw.recommended_actions,
        citations=citations,
    )
