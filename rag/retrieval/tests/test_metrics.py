import math

import pytest

from aegis_rag_retrieval.metrics import latency_summary, query_metrics


def test_hand_calculated_rank_metrics() -> None:
    metrics = query_metrics(
        ["x", "relevant-1", "y", "relevant-2"],
        {"relevant-1": 2, "relevant-2": 1},
    )
    assert metrics["recall@1"] == 0
    assert metrics["recall@3"] == 0.5
    assert metrics["recall@5"] == 1
    assert metrics["hit@1"] == 0
    assert metrics["hit@3"] == 1
    assert metrics["mrr@10"] == 0.5
    expected_dcg = 3 / math.log2(3) + 1 / math.log2(5)
    expected_idcg = 3 / math.log2(2) + 1 / math.log2(3)
    assert metrics["ndcg@5"] == pytest.approx(expected_dcg / expected_idcg)


def test_latency_percentiles_are_interpolated() -> None:
    result = latency_summary([1.0, 2.0, 3.0, 4.0])
    assert result["p50_seconds"] == 2.5
    assert result["mean_seconds"] == 2.5
    assert result["p95_seconds"] == pytest.approx(3.85)
