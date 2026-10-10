from aegis_rag_evaluation.abstention import abstention_metrics


def test_status_confusion_and_rates() -> None:
    result = abstention_metrics(
        [
            ("grounded", "grounded"),
            ("grounded", "insufficient_evidence"),
            ("insufficient_evidence", "insufficient_evidence"),
            ("insufficient_evidence", "grounded"),
        ]
    )
    assert result["supported_query_answer_rate"] == 0.5
    assert result["false_abstention_rate"] == 0.5
    assert result["unsupported_query_abstention_rate"] == 0.5
    assert result["unsupported_query_false_answer_rate"] == 0.5
    assert set(result["confusion_matrix"].values()) == {1}
