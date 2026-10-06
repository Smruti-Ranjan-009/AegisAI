from __future__ import annotations

from dataclasses import replace

import pytest

from aegis_features.aggregation import (
    build_metric_windows,
    build_service_windows,
    percentile,
)
from aegis_features.loaders import iter_signal_records, load_manifest
from aegis_features.otlp import normalize_record


def _fixture_observations(raw_root, run_id):
    run = load_manifest(raw_root, run_id)
    metrics = normalize_record(next(iter_signal_records(run, "metrics"))).metrics
    logs = normalize_record(next(iter_signal_records(run, "logs"))).logs
    spans = normalize_record(next(iter_signal_records(run, "traces"))).spans
    return metrics, logs, spans


def test_percentiles_use_linear_interpolation() -> None:
    assert percentile([], 0.5) is None
    assert percentile([1.0], 0.95) == 1.0
    assert percentile([0.0, 10.0], 0.95) == pytest.approx(9.5)


def test_service_log_and_trace_features(fixture_raw_root, fixture_run_id) -> None:
    metrics, logs, spans = _fixture_observations(fixture_raw_root, fixture_run_id)
    rows = build_service_windows(metrics, logs, spans, 60)
    assert len(rows) == 1
    row = rows[0]
    assert row["log_count"] == 3
    assert row["log_unspecified_count"] == 1
    assert row["log_warn_rate"] == pytest.approx(1 / 3)
    assert row["log_error_rate"] == pytest.approx(1 / 3)
    assert row["span_count"] == 3
    assert row["span_error_count"] == 1
    assert row["span_duration_ms_min"] == 100.0
    assert row["span_duration_ms_max"] == 200.0
    assert row["span_exception_event_count"] == 1
    assert row["metric_name_count"] == 5


def test_empty_signal_semantics_keep_window_and_nullable_statistics(
    fixture_raw_root, fixture_run_id
) -> None:
    metrics, _, _ = _fixture_observations(fixture_raw_root, fixture_run_id)
    row = build_service_windows(metrics, [], [], 60)[0]
    assert row["log_count"] == 0
    assert row["log_error_rate"] == 0.0
    assert row["log_body_bytes_mean"] is None
    assert row["span_count"] == 0
    assert row["span_duration_ms_p95"] is None


def test_metric_windows_keep_name_unit_and_type_separate(fixture_raw_root, fixture_run_id) -> None:
    metrics, _, _ = _fixture_observations(fixture_raw_root, fixture_run_id)
    rows = build_metric_windows(metrics, 60)
    assert len(rows) == 5
    by_name = {row["metric_name"]: row for row in rows}
    gauge = by_name["cpu.utilization"]
    assert gauge["metric_series_count"] == 2
    assert gauge["metric_value_mean"] == pytest.approx(0.6)
    assert gauge["metric_value_p95"] == pytest.approx(0.69)
    assert gauge["histogram_sum"] is None
    histogram = by_name["latency"]
    assert histogram["histogram_observation_count"] == 2
    assert histogram["histogram_mean"] == 15.0
    assert histogram["histogram_min"] == 5.0
    assert histogram["histogram_max"] == 25.0
    exponential = by_name["payload"]
    assert exponential["histogram_mean"] == 5.0
    summary = by_name["queue"]
    assert summary["summary_observation_count"] == 2
    assert summary["summary_mean"] == 4.0


def test_multiple_runs_never_share_a_window(fixture_raw_root, fixture_run_id) -> None:
    metrics, logs, spans = _fixture_observations(fixture_raw_root, fixture_run_id)
    second_metrics = [
        replace(metric, run_id="20260101T000000Z-normal-bbbbbb") for metric in metrics
    ]
    rows = build_service_windows([*metrics, *second_metrics], logs, spans, 60)
    assert {row["run_id"] for row in rows} == {
        fixture_run_id,
        "20260101T000000Z-normal-bbbbbb",
    }
    assert len({row["window_id"] for row in rows}) == len(rows)


def test_multiple_services_never_share_a_window(fixture_raw_root, fixture_run_id) -> None:
    metrics, _, _ = _fixture_observations(fixture_raw_root, fixture_run_id)
    payment = replace(metrics[0], service_name="payment", source_event_id="payment-event")
    rows = build_service_windows([metrics[0], payment], [], [], 60)
    assert [row["service_name"] for row in rows] == ["checkout", "payment"]


def test_conflicting_labels_in_one_run_window_are_rejected(
    fixture_raw_root, fixture_run_id
) -> None:
    metrics, _, _ = _fixture_observations(fixture_raw_root, fixture_run_id)
    conflicting = replace(metrics[0], scenario="cpu_saturation", label="cpu_saturation")
    with pytest.raises(ValueError, match="Conflicting labels"):
        build_service_windows([metrics[0], conflicting], [], [], 60)


def test_same_metric_name_with_different_unit_or_type_stays_separate(
    fixture_raw_root, fixture_run_id
) -> None:
    metrics, _, _ = _fixture_observations(fixture_raw_root, fixture_run_id)
    gauge = metrics[0]
    bytes_gauge = replace(gauge, unit="By", source_event_id="bytes")
    sum_metric = replace(gauge, metric_type="Sum", source_event_id="sum")
    rows = build_metric_windows([gauge, bytes_gauge, sum_metric], 60)
    assert len(rows) == 3
    assert {(row["unit"], row["metric_type"]) for row in rows} == {
        ("1", "Gauge"),
        ("By", "Gauge"),
        ("1", "Sum"),
    }
