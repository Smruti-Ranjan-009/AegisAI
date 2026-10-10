from __future__ import annotations


def abstention_metrics(rows: list[tuple[str, str]]) -> dict[str, object]:
    matrix = {
        "expected_grounded_predicted_grounded": 0,
        "expected_grounded_predicted_insufficient_evidence": 0,
        "expected_insufficient_evidence_predicted_grounded": 0,
        "expected_insufficient_evidence_predicted_insufficient_evidence": 0,
    }
    for expected, predicted in rows:
        key = f"expected_{expected}_predicted_{predicted}"
        if key not in matrix:
            raise ValueError(f"invalid status pair: {expected}/{predicted}")
        matrix[key] += 1
    supported = sum(expected == "grounded" for expected, _ in rows)
    unsupported = len(rows) - supported
    supported_answers = matrix["expected_grounded_predicted_grounded"]
    correct_abstentions = matrix[
        "expected_insufficient_evidence_predicted_insufficient_evidence"
    ]
    false_answers = matrix["expected_insufficient_evidence_predicted_grounded"]
    return {
        "confusion_matrix": matrix,
        "supported_query_answer_rate": supported_answers / supported if supported else None,
        "false_abstention_rate": (supported - supported_answers) / supported if supported else None,
        "unsupported_query_abstention_rate": correct_abstentions / unsupported
        if unsupported
        else None,
        "unsupported_query_false_answer_rate": false_answers / unsupported
        if unsupported
        else None,
    }
