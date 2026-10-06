from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .config import UNKNOWN_SERVICE
from .contracts import feature_columns
from .errors import DataQualityError
from .observations import LogObservation, MetricObservation, SpanObservation


@dataclass
class QualityCounters:
    input_records: int = 0
    duplicate_records_removed: int = 0
    invalid_duration_count: int = 0
    non_finite_numeric_values: int = 0
    observations_by_signal: Counter[str] = field(default_factory=Counter)
    observations_by_service: Counter[str] = field(default_factory=Counter)
    missing_timestamps_by_signal: Counter[str] = field(default_factory=Counter)

    @property
    def observation_count(self) -> int:
        return sum(self.observations_by_signal.values())

    @property
    def missing_timestamp_count(self) -> int:
        return sum(self.missing_timestamps_by_signal.values())

    @property
    def unknown_service_observations(self) -> int:
        return self.observations_by_service[UNKNOWN_SERVICE]


def observe(
    counters: QualityCounters,
    signal: str,
    observations: Iterable[MetricObservation | LogObservation | SpanObservation],
) -> None:
    for observation in observations:
        counters.observations_by_signal[signal] += 1
        counters.observations_by_service[observation.service_name] += 1
        if observation.timestamp_ns is None:
            counters.missing_timestamps_by_signal[signal] += 1
        if isinstance(observation, SpanObservation) and observation.invalid_duration:
            counters.invalid_duration_count += 1
        numeric_values: tuple[float | None, ...] = ()
        if isinstance(observation, MetricObservation):
            numeric_values = (
                observation.numeric_value,
                observation.aggregate_sum,
                observation.aggregate_min,
                observation.aggregate_max,
            )
        elif isinstance(observation, SpanObservation):
            numeric_values = (observation.duration_ms,)
        counters.non_finite_numeric_values += sum(
            value is not None and not math.isfinite(value) for value in numeric_values
        )


def validate_observations(counters: QualityCounters, max_invalid_ratio: float) -> None:
    if counters.non_finite_numeric_values:
        raise DataQualityError(
            f"Found {counters.non_finite_numeric_values} non-finite observation values"
        )
    if counters.observation_count == 0:
        raise DataQualityError("No telemetry observations were found")
    ratio = counters.missing_timestamp_count / counters.observation_count
    if ratio > max_invalid_ratio:
        raise DataQualityError(
            f"Missing/invalid timestamp ratio {ratio:.6f} exceeds limit {max_invalid_ratio:.6f}"
        )


def validate_feature_rows(rows: list[dict[str, Any]], dataset: str) -> None:
    for row_index, row in enumerate(rows):
        if row["window_end_utc"] <= row["window_start_utc"]:
            raise DataQualityError(f"Invalid window bounds in {dataset} row {row_index}")
        for column in feature_columns(dataset):
            value = row[column]
            if isinstance(value, float) and not math.isfinite(value):
                raise DataQualityError(
                    f"Non-finite feature {column!r} in {dataset} row {row_index}"
                )
            if column.endswith("_count") and value is not None and value < 0:
                raise DataQualityError(f"Negative count {column!r} in {dataset} row {row_index}")
        for rate in ("log_warn_rate", "log_error_rate", "log_fatal_rate", "span_error_rate"):
            if rate in row and not 0 <= row[rate] <= 1:
                raise DataQualityError(f"Rate {rate!r} is outside [0, 1]")
        for duration in (
            "span_duration_ms_mean",
            "span_duration_ms_min",
            "span_duration_ms_max",
            "span_duration_ms_p50",
            "span_duration_ms_p95",
            "span_duration_ms_p99",
        ):
            if duration in row and row[duration] is not None and row[duration] < 0:
                raise DataQualityError(f"Negative duration {duration!r}")


def quality_report(
    counters: QualityCounters,
    service_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    max_invalid_ratio: float,
) -> dict[str, Any]:
    class_distribution = Counter(str(row["label"]) for row in service_rows)
    scenario_distribution = Counter(str(row["scenario"]) for row in service_rows)
    return {
        "status": "PASS",
        "observation_counts_by_signal": dict(sorted(counters.observations_by_signal.items())),
        "observation_counts_by_service": dict(sorted(counters.observations_by_service.items())),
        "service_window_count": len(service_rows),
        "metric_window_count": len(metric_rows),
        "class_distribution": dict(sorted(class_distribution.items())),
        "scenario_distribution": dict(sorted(scenario_distribution.items())),
        "missing_timestamp_counts": dict(sorted(counters.missing_timestamps_by_signal.items())),
        "missing_timestamp_ratio": (
            counters.missing_timestamp_count / counters.observation_count
            if counters.observation_count
            else 0.0
        ),
        "max_invalid_observation_ratio": max_invalid_ratio,
        "invalid_duration_count": counters.invalid_duration_count,
        "unknown_service_observations": counters.unknown_service_observations,
        "non_finite_numeric_values": counters.non_finite_numeric_values,
        "duplicate_source_records": counters.duplicate_records_removed,
        "empty_windows": 0,
        "dropped_observations": counters.missing_timestamp_count,
    }
