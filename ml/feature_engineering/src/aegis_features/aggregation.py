from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import FEATURE_SCHEMA_VERSION
from .observations import LogObservation, MetricObservation, SpanObservation
from .windows import metric_window_id, ns_to_utc, service_window_id, window_start_ns


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


@dataclass
class ServiceAccumulator:
    run_id: str
    scenario: str
    label: str
    service_name: str
    window_start: datetime
    source_event_ids: set[str] = field(default_factory=set)
    logs: list[LogObservation] = field(default_factory=list)
    spans: list[SpanObservation] = field(default_factory=list)
    metrics: list[MetricObservation] = field(default_factory=list)


@dataclass
class MetricAccumulator:
    run_id: str
    scenario: str
    label: str
    service_name: str
    window_start: datetime
    metric_name: str
    unit: str
    metric_type: str
    points: list[MetricObservation] = field(default_factory=list)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _base_row(accumulator: ServiceAccumulator, window_seconds: int) -> dict[str, object]:
    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "window_id": service_window_id(
            accumulator.run_id,
            accumulator.service_name,
            accumulator.window_start,
            window_seconds,
        ),
        "run_id": accumulator.run_id,
        "service_name": accumulator.service_name,
        "window_start_utc": accumulator.window_start,
        "window_end_utc": accumulator.window_start + timedelta(seconds=window_seconds),
        "window_seconds": window_seconds,
        "source_event_count": len(accumulator.source_event_ids),
        "scenario": accumulator.scenario,
        "label": accumulator.label,
        "is_anomaly": accumulator.scenario != "normal",
    }


def _log_features(logs: list[LogObservation]) -> dict[str, int | float | None]:
    counts = Counter(log.severity_group for log in logs)
    total = len(logs)
    body_sizes = [log.body_bytes for log in logs]
    return {
        "log_count": total,
        "log_trace_count": counts["TRACE"],
        "log_debug_count": counts["DEBUG"],
        "log_info_count": counts["INFO"],
        "log_warn_count": counts["WARN"],
        "log_error_count": counts["ERROR"],
        "log_fatal_count": counts["FATAL"],
        "log_unspecified_count": counts["UNSPECIFIED"],
        "log_warn_rate": _rate(counts["WARN"], total),
        "log_error_rate": _rate(counts["ERROR"], total),
        "log_fatal_rate": _rate(counts["FATAL"], total),
        "log_body_bytes_mean": statistics.fmean(body_sizes) if body_sizes else None,
        "log_body_bytes_max": max(body_sizes) if body_sizes else None,
    }


def _trace_features(spans: list[SpanObservation]) -> dict[str, int | float | None]:
    total = len(spans)
    error_count = sum(span.is_error for span in spans)
    durations = [span.duration_ms for span in spans if span.duration_ms is not None]
    kinds = Counter(span.span_kind for span in spans)
    return {
        "span_count": total,
        "span_error_count": error_count,
        "span_error_rate": _rate(error_count, total),
        "span_duration_ms_mean": statistics.fmean(durations) if durations else None,
        "span_duration_ms_min": min(durations) if durations else None,
        "span_duration_ms_max": max(durations) if durations else None,
        "span_duration_ms_p50": percentile(durations, 0.50),
        "span_duration_ms_p95": percentile(durations, 0.95),
        "span_duration_ms_p99": percentile(durations, 0.99),
        "span_internal_count": kinds["INTERNAL"],
        "span_server_count": kinds["SERVER"],
        "span_client_count": kinds["CLIENT"],
        "span_producer_count": kinds["PRODUCER"],
        "span_consumer_count": kinds["CONSUMER"],
        "span_unspecified_count": kinds["UNSPECIFIED"],
        "span_unique_operation_count": len({span.operation_name for span in spans}),
        "span_exception_event_count": sum(span.exception_event_count for span in spans),
    }


def _metric_volume_features(metrics: list[MetricObservation]) -> dict[str, int]:
    types = Counter(metric.metric_type for metric in metrics)
    return {
        "metric_name_count": len({metric.metric_name for metric in metrics}),
        "metric_point_count": len(metrics),
        "metric_gauge_count": types["Gauge"],
        "metric_sum_count": types["Sum"],
        "metric_histogram_count": types["Histogram"],
        "metric_exponential_histogram_count": types["ExponentialHistogram"],
        "metric_summary_count": types["Summary"],
    }


def build_service_windows(
    metrics: list[MetricObservation],
    logs: list[LogObservation],
    spans: list[SpanObservation],
    window_seconds: int,
) -> list[dict[str, object]]:
    windows: dict[tuple[str, str, int], ServiceAccumulator] = {}
    signal_groups = (("metrics", metrics), ("logs", logs), ("spans", spans))
    for signal, observations in signal_groups:
        for observation in observations:
            if observation.timestamp_ns is None:
                continue
            start_ns = window_start_ns(observation.timestamp_ns, window_seconds)
            key = (observation.run_id, observation.service_name, start_ns)
            accumulator = windows.setdefault(
                key,
                ServiceAccumulator(
                    run_id=observation.run_id,
                    scenario=observation.scenario,
                    label=observation.label,
                    service_name=observation.service_name,
                    window_start=ns_to_utc(start_ns),
                ),
            )
            if (
                accumulator.scenario != observation.scenario
                or accumulator.label != observation.label
            ):
                raise ValueError(f"Conflicting labels in service window: {key}")
            accumulator.source_event_ids.add(observation.source_event_id)
            getattr(accumulator, signal).append(observation)

    rows: list[dict[str, object]] = []
    for accumulator in windows.values():
        row = _base_row(accumulator, window_seconds)
        row.update(_log_features(accumulator.logs))
        row.update(_trace_features(accumulator.spans))
        row.update(_metric_volume_features(accumulator.metrics))
        row["telemetry_observation_count"] = (
            len(accumulator.logs) + len(accumulator.spans) + len(accumulator.metrics)
        )
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (row["run_id"], row["window_start_utc"], row["service_name"]),
    )


def _metric_row(accumulator: MetricAccumulator, window_seconds: int) -> dict[str, object]:
    points = accumulator.points
    numeric_points = [point for point in points if point.numeric_value is not None]
    numeric_values = [point.numeric_value for point in numeric_points]
    ordered_numeric = sorted(
        numeric_points,
        key=lambda point: (point.timestamp_ns or 0, point.series_identity, point.source_event_id),
    )
    is_histogram = accumulator.metric_type in {"Histogram", "ExponentialHistogram"}
    is_summary = accumulator.metric_type == "Summary"
    aggregate_points = [point for point in points if point.aggregate_count is not None]
    observation_count = sum(point.aggregate_count or 0 for point in aggregate_points)
    sums = [point.aggregate_sum for point in aggregate_points if point.aggregate_sum is not None]
    minima = [point.aggregate_min for point in aggregate_points if point.aggregate_min is not None]
    maxima = [point.aggregate_max for point in aggregate_points if point.aggregate_max is not None]
    aggregate_sum = sum(sums) if len(sums) == len(aggregate_points) and sums else None
    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "metric_window_id": metric_window_id(
            accumulator.run_id,
            accumulator.service_name,
            accumulator.window_start,
            window_seconds,
            accumulator.metric_name,
            accumulator.unit,
            accumulator.metric_type,
        ),
        "run_id": accumulator.run_id,
        "service_name": accumulator.service_name,
        "window_start_utc": accumulator.window_start,
        "window_end_utc": accumulator.window_start + timedelta(seconds=window_seconds),
        "window_seconds": window_seconds,
        "metric_name": accumulator.metric_name,
        "unit": accumulator.unit,
        "metric_type": accumulator.metric_type,
        "scenario": accumulator.scenario,
        "label": accumulator.label,
        "is_anomaly": accumulator.scenario != "normal",
        "metric_point_count": len(points),
        "metric_series_count": len({point.series_identity for point in points}),
        "metric_value_mean": statistics.fmean(numeric_values) if numeric_values else None,
        "metric_value_std": statistics.pstdev(numeric_values) if numeric_values else None,
        "metric_value_min": min(numeric_values) if numeric_values else None,
        "metric_value_max": max(numeric_values) if numeric_values else None,
        "metric_value_p50": percentile(numeric_values, 0.50),
        "metric_value_p95": percentile(numeric_values, 0.95),
        "metric_value_p99": percentile(numeric_values, 0.99),
        "metric_value_first": ordered_numeric[0].numeric_value if ordered_numeric else None,
        "metric_value_last": ordered_numeric[-1].numeric_value if ordered_numeric else None,
        "histogram_datapoint_count": len(aggregate_points) if is_histogram else 0,
        "histogram_observation_count": observation_count if is_histogram else 0,
        "histogram_sum": aggregate_sum if is_histogram else None,
        "histogram_mean": (
            aggregate_sum / observation_count
            if is_histogram and aggregate_sum is not None and observation_count
            else None
        ),
        "histogram_min": min(minima) if is_histogram and minima else None,
        "histogram_max": max(maxima) if is_histogram and maxima else None,
        "summary_datapoint_count": len(aggregate_points) if is_summary else 0,
        "summary_observation_count": observation_count if is_summary else 0,
        "summary_sum": aggregate_sum if is_summary else None,
        "summary_mean": (
            aggregate_sum / observation_count
            if is_summary and aggregate_sum is not None and observation_count
            else None
        ),
    }


def build_metric_windows(
    metrics: list[MetricObservation], window_seconds: int
) -> list[dict[str, object]]:
    windows: dict[tuple[str, str, int, str, str, str], MetricAccumulator] = {}
    for observation in metrics:
        if observation.timestamp_ns is None:
            continue
        start_ns = window_start_ns(observation.timestamp_ns, window_seconds)
        key = (
            observation.run_id,
            observation.service_name,
            start_ns,
            observation.metric_name,
            observation.unit,
            observation.metric_type,
        )
        accumulator = windows.setdefault(
            key,
            MetricAccumulator(
                run_id=observation.run_id,
                scenario=observation.scenario,
                label=observation.label,
                service_name=observation.service_name,
                window_start=ns_to_utc(start_ns),
                metric_name=observation.metric_name,
                unit=observation.unit,
                metric_type=observation.metric_type,
            ),
        )
        if accumulator.scenario != observation.scenario or accumulator.label != observation.label:
            raise ValueError(f"Conflicting labels in metric window: {key}")
        accumulator.points.append(observation)

    rows = [_metric_row(accumulator, window_seconds) for accumulator in windows.values()]
    return sorted(
        rows,
        key=lambda row: (
            row["run_id"],
            row["window_start_utc"],
            row["service_name"],
            row["metric_name"],
            row["unit"],
            row["metric_type"],
        ),
    )
