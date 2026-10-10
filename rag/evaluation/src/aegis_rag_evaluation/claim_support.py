from __future__ import annotations

from time import perf_counter

from aegis_rag_evaluation.contracts import NLIPrediction, NLIProvider
from aegis_rag_evaluation.gold import ordered_evidence_text


def evaluate_claim_support(
    artifact: dict[str, object], provider: NLIProvider
) -> dict[str, object]:
    response = artifact["structured_response"]
    evidence = artifact["evidence"]
    claims: list[tuple[str, str, list[str]]] = []
    for kind, field, text_key in (
        ("cause", "suspected_causes", "cause"),
        ("action", "recommended_actions", "action"),
    ):
        for item in response[field]:
            claims.append((kind, str(item[text_key]), [str(value) for value in item["evidence"]]))
    pairs = [(ordered_evidence_text(ids, evidence), text) for _, text, ids in claims]
    started = perf_counter()
    predictions = provider.predict(pairs)
    if len(predictions) != len(claims):
        raise ValueError("NLI provider returned the wrong claim count")
    rows = [
        {
            "claim_type": kind,
            "claim": text,
            "evidence_ids": ids,
            **_prediction_dict(prediction),
        }
        for (kind, text, ids), prediction in zip(claims, predictions, strict=True)
    ]
    citation_ids = [str(item["evidence_id"]) for item in response["citations"]]
    summary_prediction = None
    if response["status"] == "grounded" and citation_ids:
        result = provider.predict(
            [(ordered_evidence_text(citation_ids, evidence), str(response["summary"]))]
        )
        if len(result) != 1:
            raise ValueError("NLI provider returned the wrong summary count")
        summary_prediction = _prediction_dict(result[0])
    counts = {label: sum(row["label"] == label for row in rows) for label in (
        "entailment", "contradiction", "neutral"
    )}
    total = len(rows)
    return {
        "claims": rows,
        "claim_count": total,
        "supported_claims": counts["entailment"],
        "contradicted_claims": counts["contradiction"],
        "neutral_claims": counts["neutral"],
        "nli_supported_claim_rate": counts["entailment"] / total if total else None,
        "unsupported_claim_rate": (counts["contradiction"] + counts["neutral"]) / total
        if total
        else None,
        "contradiction_rate": counts["contradiction"] / total if total else None,
        "neutral_rate": counts["neutral"] / total if total else None,
        "summary_support_proxy": summary_prediction,
        "evaluation_seconds": perf_counter() - started,
    }


def _prediction_dict(prediction: NLIPrediction) -> dict[str, object]:
    return {
        "label": prediction.label,
        "probabilities": prediction.probabilities,
        "input_tokens": prediction.input_tokens,
        "truncated": prediction.truncated,
    }
