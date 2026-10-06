from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ObservationIdentity:
    run_id: str
    scenario: str
    label: str
    service_name: str
    timestamp_ns: int | None
    source_event_id: str
    resource_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class MetricObservation(ObservationIdentity):
    metric_name: str
    unit: str
    metric_type: str
    series_identity: str
    numeric_value: float | None = None
    aggregate_count: int | None = None
    aggregate_sum: float | None = None
    aggregate_min: float | None = None
    aggregate_max: float | None = None


@dataclass(frozen=True, kw_only=True)
class LogObservation(ObservationIdentity):
    severity_number: int
    severity_group: str
    body_bytes: int


@dataclass(frozen=True, kw_only=True)
class SpanObservation(ObservationIdentity):
    operation_name: str
    span_kind: str
    is_error: bool
    duration_ms: float | None
    exception_event_count: int
    invalid_duration: bool = False
