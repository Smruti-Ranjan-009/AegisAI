from __future__ import annotations

from aegis_rag_evaluation.contracts import GoldRecord, NLIProvider
from aegis_rag_evaluation.gold import structured_answer_text


def evaluate_completeness(
    artifact: dict[str, object], gold: GoldRecord, provider: NLIProvider
) -> dict[str, object]:
    if gold.expected_status == "insufficient_evidence":
        return {
            "excluded": True,
            "nli_expected_fact_coverage": None,
            "reference_action_coverage": None,
            "facts": [],
            "actions": [],
        }
    answer = structured_answer_text(artifact["structured_response"])
    fact_predictions = provider.predict([(answer, fact) for fact in gold.required_facts])
    action_predictions = provider.predict([(answer, action) for action in gold.acceptable_actions])
    facts = _rows(gold.required_facts, fact_predictions)
    actions = _rows(gold.acceptable_actions, action_predictions)
    return {
        "excluded": False,
        "facts": facts,
        "covered_facts": sum(row["label"] == "entailment" for row in facts),
        "fact_count": len(facts),
        "nli_expected_fact_coverage": _coverage(facts),
        "actions": actions,
        "covered_actions": sum(row["label"] == "entailment" for row in actions),
        "action_count": len(actions),
        "reference_action_coverage": _coverage(actions),
    }


def _rows(statements, predictions):
    if len(statements) != len(predictions):
        raise ValueError("NLI provider returned the wrong completeness result count")
    return [
        {
            "statement": statement,
            "label": prediction.label,
            "probabilities": prediction.probabilities,
            "input_tokens": prediction.input_tokens,
            "truncated": prediction.truncated,
        }
        for statement, prediction in zip(statements, predictions, strict=True)
    ]


def _coverage(rows: list[dict[str, object]]) -> float:
    return sum(row["label"] == "entailment" for row in rows) / len(rows) if rows else 0.0
