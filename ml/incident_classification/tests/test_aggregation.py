from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aegis_classifier.aggregation import aggregate_runs
from aegis_classifier.anomaly_adapter import ScoredWindow
from aegis_classifier.config import AggregationConfig
from aegis_classifier.errors import ClassificationError


def _features(value: float) -> dict[str, float]:
    return {
        "metric_abs_deviation_mean": value,
        "metric_abs_deviation_max": value + 1,
        "metric_abs_deviation_p95": value + 0.5,
        "metric_deviation_over_3_count": value,
        "metric_deviation_over_5_count": value / 2,
        "metric_coverage_ratio": 0.8,
        "metric_missing_baseline_count": 1,
        "log_count": value * 10,
        "log_warn_rate": value / 10,
        "log_error_rate": value / 20,
        "log_fatal_rate": 0,
        "span_count": value * 20,
        "span_error_rate": value / 15,
        "span_duration_ms_mean": value * 5,
        "span_duration_ms_p95": value * 8,
        "span_duration_ms_p99": value * 10,
        "span_exception_event_count": value,
        "metric_point_count": value * 30,
        "metric_name_count": value * 2,
        "telemetry_observation_count": value * 60,
    }


def _window(service: str, score: float, value: float, window_id: str) -> ScoredWindow:
    return ScoredWindow(
        "run-1",
        "cpu_saturation",
        service,
        window_id,
        datetime(2026, 1, 1, tzinfo=UTC),
        score,
        score > 0.5,
        _features(value),
    )


def test_top_three_ranking_and_aggregation_are_deterministic() -> None:
    rows = [
        _window("zeta", 0.7, 7, "4"),
        _window("alpha", 0.9, 9, "2"),
        _window("beta", 0.9, 8, "1"),
        _window("gamma", 0.8, 6, "3"),
    ]
    first = aggregate_runs(rows)[0]
    second = aggregate_runs(list(reversed(rows)))[0]
    assert first == second
    assert first["anomaly_score_max"] == pytest.approx(0.9)
    assert first["anomaly_score_min_top3"] == pytest.approx(0.8)
    assert first["eligible_window_count"] == 4
    assert first["anomaly_threshold_exceed_count"] == 4
    assert first["log_count_top3_sum"] == pytest.approx((9 + 8 + 6) * 10)


def test_multiple_service_windows_create_exactly_one_run_row() -> None:
    result = aggregate_runs([_window("ad", 0.8, 3, "1"), _window("cart", 0.4, 2, "2")])
    assert len(result) == 1
    assert "service_name" not in result[0]


def test_normal_is_not_a_classifier_target() -> None:
    row = _window("ad", 0.8, 3, "1")
    row = ScoredWindow(**{**row.__dict__, "scenario": "normal"})
    with pytest.raises(ClassificationError, match="cannot contain"):
        aggregate_runs([row], AggregationConfig())
