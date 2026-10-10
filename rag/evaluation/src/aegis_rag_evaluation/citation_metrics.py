from __future__ import annotations

from aegis_rag_evaluation.contracts import GoldRecord
from aegis_rag_evaluation.gold import section_key


def structural_citation_validity(artifact: dict[str, object]) -> dict[str, object]:
    response = artifact["structured_response"]
    evidence = artifact["evidence"]
    evidence_map = {str(item["evidence_id"]): item for item in evidence}
    citations = response["citations"]
    citation_ids = [str(item["evidence_id"]) for item in citations]
    claim_ids = [
        str(evidence_id)
        for field in ("suspected_causes", "recommended_actions")
        for claim in response[field]
        for evidence_id in claim["evidence"]
    ]
    reasons: list[str] = []
    if len(citation_ids) != len(set(citation_ids)):
        reasons.append("duplicate_citation")
    if set(citation_ids) != set(claim_ids):
        reasons.append("citation_claim_mismatch")
    for citation in citations:
        evidence_id = str(citation["evidence_id"])
        supplied = evidence_map.get(evidence_id)
        if supplied is None:
            reasons.append("unknown_evidence_id")
            continue
        if citation["source_path"] != supplied["source_path"]:
            reasons.append("source_path_mismatch")
        if list(citation["heading_path"]) != list(supplied["heading_path"]):
            reasons.append("heading_path_mismatch")
    if response["status"] == "grounded" and not citations:
        reasons.append("grounded_without_citation")
    if response["status"] == "insufficient_evidence" and citations:
        reasons.append("insufficient_with_citation")
    return {"valid": not reasons, "reasons": sorted(set(reasons))}


def gold_citation_metrics(
    citations: list[dict[str, object]], gold: GoldRecord
) -> dict[str, float | int]:
    cited = {section_key(item) for item in citations}
    all_gold = {section.key for section in gold.relevant_sections}
    direct = {section.key for section in gold.relevant_sections if section.grade == 2}
    all_hits = cited & all_gold
    direct_hits = cited & direct
    return {
        "cited_sections": len(cited),
        "all_relevant_sections": len(all_gold),
        "direct_sections": len(direct),
        "all_relevant_hits": len(all_hits),
        "direct_hits": len(direct_hits),
        "precision": len(all_hits) / len(cited) if cited else 0.0,
        "recall": len(all_hits) / len(all_gold) if all_gold else 0.0,
        "direct_precision": len(direct_hits) / len(cited) if cited else 0.0,
        "direct_recall": len(direct_hits) / len(direct) if direct else 0.0,
    }
