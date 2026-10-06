from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from google.protobuf import json_format
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource

from .config import UNKNOWN_SERVICE
from .errors import InputValidationError
from .loaders import SourceRecord
from .observations import LogObservation, MetricObservation, SpanObservation

REQUEST_TYPES = {
    "metrics": ExportMetricsServiceRequest,
    "logs": ExportLogsServiceRequest,
    "traces": ExportTraceServiceRequest,
}


@dataclass
class NormalizedBatch:
    metrics: list[MetricObservation] = field(default_factory=list)
    logs: list[LogObservation] = field(default_factory=list)
    spans: list[SpanObservation] = field(default_factory=list)

    @property
    def observations(self) -> list[MetricObservation | LogObservation | SpanObservation]:
        return [*self.metrics, *self.logs, *self.spans]


def any_value_to_python(value: AnyValue) -> Any:
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [any_value_to_python(item) for item in value.array_value.values]
    if kind == "kvlist_value":
        return {
            item.key: any_value_to_python(item.value)
            for item in value.kvlist_value.values
        }
    if kind == "bytes_value":
        return bytes(value.bytes_value)
    return getattr(value, kind)


def attributes_to_dict(attributes: Iterable[KeyValue]) -> dict[str, Any]:
    return {attribute.key: any_value_to_python(attribute.value) for attribute in attributes}


def resource_context(resource: Resource) -> tuple[str, dict[str, Any]]:
    attributes = attributes_to_dict(resource.attributes)
    service = attributes.get("service.name")
    if not isinstance(service, str) or not service.strip():
        service = UNKNOWN_SERVICE
    return service, attributes


def parse_export_request(signal: str, document: dict[str, Any]) -> Any:
    request_type = REQUEST_TYPES.get(signal)
    if request_type is None:
        raise InputValidationError(f"Unsupported signal: {signal!r}")
    try:
        return json_format.ParseDict(document, request_type(), ignore_unknown_fields=False)
    except (json_format.ParseError, ValueError, TypeError) as exc:
        raise InputValidationError(f"Invalid OTLP {signal} export request: {exc}") from exc


def _timestamp(value: int) -> int | None:
    return int(value) if value > 0 else None


def _series_identity(attributes: Iterable[KeyValue]) -> str:
    canonical = json.dumps(
        attributes_to_dict(attributes),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_base64": base64.b64encode(value).decode("ascii")}
    raise TypeError(f"Unsupported AnyValue result: {type(value).__name__}")


def _body_bytes(value: AnyValue) -> int:
    body = any_value_to_python(value)
    if isinstance(body, bytes):
        return len(body)
    if isinstance(body, str):
        return len(body.encode("utf-8"))
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode("utf-8")
    return len(encoded)


def severity_group(number: int) -> str:
    if 1 <= number <= 4:
        return "TRACE"
    if 5 <= number <= 8:
        return "DEBUG"
    if 9 <= number <= 12:
        return "INFO"
    if 13 <= number <= 16:
        return "WARN"
    if 17 <= number <= 20:
        return "ERROR"
    if 21 <= number <= 24:
        return "FATAL"
    return "UNSPECIFIED"


def _numeric_value(point: Any) -> float | None:
    kind = point.WhichOneof("value")
    if kind not in {"as_double", "as_int"}:
        return None
    value = float(getattr(point, kind))
    return value


def _optional_number(message: Any, field_name: str) -> float | None:
    try:
        if not message.HasField(field_name):
            return None
    except ValueError:
        pass
    value = float(getattr(message, field_name))
    return value if math.isfinite(value) else value


def _metric_observation(
    record: SourceRecord,
    service_name: str,
    resource_attributes: dict[str, Any],
    metric: Any,
    metric_type: str,
    point: Any,
    *,
    numeric_value: float | None = None,
    aggregate_count: int | None = None,
    aggregate_sum: float | None = None,
    aggregate_min: float | None = None,
    aggregate_max: float | None = None,
) -> MetricObservation:
    return MetricObservation(
        run_id=record.run.run_id,
        scenario=record.run.scenario,
        label=record.run.label,
        service_name=service_name,
        timestamp_ns=_timestamp(point.time_unix_nano),
        source_event_id=record.source_event_id,
        resource_attributes=resource_attributes,
        metric_name=metric.name,
        unit=metric.unit,
        metric_type=metric_type,
        series_identity=_series_identity(point.attributes),
        numeric_value=numeric_value,
        aggregate_count=aggregate_count,
        aggregate_sum=aggregate_sum,
        aggregate_min=aggregate_min,
        aggregate_max=aggregate_max,
    )


def normalize_metrics(
    record: SourceRecord, request: ExportMetricsServiceRequest
) -> list[MetricObservation]:
    result: list[MetricObservation] = []
    for resource_metrics in request.resource_metrics:
        service, resource_attributes = resource_context(resource_metrics.resource)
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                metric_kind = metric.WhichOneof("data")
                if metric_kind in {"gauge", "sum"}:
                    metric_type = "Gauge" if metric_kind == "gauge" else "Sum"
                    for point in getattr(metric, metric_kind).data_points:
                        result.append(
                            _metric_observation(
                                record,
                                service,
                                resource_attributes,
                                metric,
                                metric_type,
                                point,
                                numeric_value=_numeric_value(point),
                            )
                        )
                elif metric_kind in {"histogram", "exponential_histogram"}:
                    metric_type = (
                        "Histogram" if metric_kind == "histogram" else "ExponentialHistogram"
                    )
                    for point in getattr(metric, metric_kind).data_points:
                        result.append(
                            _metric_observation(
                                record,
                                service,
                                resource_attributes,
                                metric,
                                metric_type,
                                point,
                                aggregate_count=int(point.count),
                                aggregate_sum=_optional_number(point, "sum"),
                                aggregate_min=_optional_number(point, "min"),
                                aggregate_max=_optional_number(point, "max"),
                            )
                        )
                elif metric_kind == "summary":
                    for point in metric.summary.data_points:
                        result.append(
                            _metric_observation(
                                record,
                                service,
                                resource_attributes,
                                metric,
                                "Summary",
                                point,
                                aggregate_count=int(point.count),
                                aggregate_sum=float(point.sum),
                            )
                        )
                elif metric_kind is not None:
                    raise InputValidationError(f"Unsupported OTLP metric type: {metric_kind}")
    return result


def normalize_logs(record: SourceRecord, request: ExportLogsServiceRequest) -> list[LogObservation]:
    result: list[LogObservation] = []
    for resource_logs in request.resource_logs:
        service, resource_attributes = resource_context(resource_logs.resource)
        for scope_logs in resource_logs.scope_logs:
            for log_record in scope_logs.log_records:
                timestamp = log_record.time_unix_nano or log_record.observed_time_unix_nano
                result.append(
                    LogObservation(
                        run_id=record.run.run_id,
                        scenario=record.run.scenario,
                        label=record.run.label,
                        service_name=service,
                        timestamp_ns=_timestamp(timestamp),
                        source_event_id=record.source_event_id,
                        resource_attributes=resource_attributes,
                        severity_number=int(log_record.severity_number),
                        severity_group=severity_group(int(log_record.severity_number)),
                        body_bytes=_body_bytes(log_record.body),
                    )
                )
    return result


SPAN_KINDS = {
    0: "UNSPECIFIED",
    1: "INTERNAL",
    2: "SERVER",
    3: "CLIENT",
    4: "PRODUCER",
    5: "CONSUMER",
}


def normalize_traces(
    record: SourceRecord, request: ExportTraceServiceRequest
) -> list[SpanObservation]:
    result: list[SpanObservation] = []
    for resource_spans in request.resource_spans:
        service, resource_attributes = resource_context(resource_spans.resource)
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                invalid_duration = span.end_time_unix_nano < span.start_time_unix_nano
                duration_ms = None
                if span.start_time_unix_nano > 0 and not invalid_duration:
                    duration_ms = (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000
                result.append(
                    SpanObservation(
                        run_id=record.run.run_id,
                        scenario=record.run.scenario,
                        label=record.run.label,
                        service_name=service,
                        timestamp_ns=_timestamp(span.start_time_unix_nano),
                        source_event_id=record.source_event_id,
                        resource_attributes=resource_attributes,
                        operation_name=span.name,
                        span_kind=SPAN_KINDS.get(int(span.kind), "UNSPECIFIED"),
                        is_error=int(span.status.code) == 2,
                        duration_ms=duration_ms,
                        exception_event_count=sum(
                            1 for event in span.events if event.name == "exception"
                        ),
                        invalid_duration=invalid_duration,
                    )
                )
    return result


def normalize_record(record: SourceRecord) -> NormalizedBatch:
    request = parse_export_request(record.signal, record.document)
    batch = NormalizedBatch()
    if record.signal == "metrics":
        batch.metrics.extend(normalize_metrics(record, request))
    elif record.signal == "logs":
        batch.logs.extend(normalize_logs(record, request))
    else:
        batch.spans.extend(normalize_traces(record, request))
    return batch
