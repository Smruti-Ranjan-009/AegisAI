from __future__ import annotations

from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue, KeyValueList

from aegis_features.loaders import iter_signal_records, load_manifest
from aegis_features.otlp import (
    any_value_to_python,
    normalize_metrics,
    normalize_record,
    parse_export_request,
    severity_group,
)


def test_any_value_conversion_supports_every_otlp_shape() -> None:
    assert any_value_to_python(AnyValue(string_value="value")) == "value"
    assert any_value_to_python(AnyValue(bool_value=True)) is True
    assert any_value_to_python(AnyValue(int_value=7)) == 7
    assert any_value_to_python(AnyValue(double_value=1.5)) == 1.5
    assert any_value_to_python(AnyValue(bytes_value=b"x")) == b"x"
    array = AnyValue(array_value=ArrayValue(values=[AnyValue(string_value="a")]))
    assert any_value_to_python(array) == ["a"]
    mapping = AnyValue(
        kvlist_value=KeyValueList(
            values=[KeyValue(key="answer", value=AnyValue(int_value=42))]
        )
    )
    assert any_value_to_python(mapping) == {"answer": 42}
    assert any_value_to_python(AnyValue()) is None


def test_fixture_normalizes_all_metric_types(fixture_raw_root, fixture_run_id) -> None:
    run = load_manifest(fixture_raw_root, fixture_run_id)
    record = next(iter_signal_records(run, "metrics"))
    batch = normalize_record(record)
    assert {metric.metric_type for metric in batch.metrics} == {
        "Gauge",
        "Sum",
        "Histogram",
        "ExponentialHistogram",
        "Summary",
    }
    assert {metric.service_name for metric in batch.metrics} == {"checkout"}
    assert all(metric.timestamp_ns is not None for metric in batch.metrics)
    assert batch.metrics[0].resource_attributes["tags"] == ["a", 3]
    assert batch.metrics[0].resource_attributes["blob"] == b"\x01\x02"


def test_missing_resource_service_uses_unknown_sentinel(fixture_raw_root, fixture_run_id) -> None:
    run = load_manifest(fixture_raw_root, fixture_run_id)
    record = next(iter_signal_records(run, "metrics"))
    document = {
        "resourceMetrics": [
            {
                "resource": {},
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "value",
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": "1767225600000000000",
                                            "asInt": "1",
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    request = parse_export_request("metrics", document)
    assert normalize_metrics(record, request)[0].service_name == "__unknown__"


def test_logs_use_event_time_fallback_and_numeric_severity(
    fixture_raw_root, fixture_run_id
) -> None:
    run = load_manifest(fixture_raw_root, fixture_run_id)
    batch = normalize_record(next(iter_signal_records(run, "logs")))
    assert [log.severity_group for log in batch.logs] == ["UNSPECIFIED", "WARN", "ERROR"]
    assert batch.logs[-1].timestamp_ns == 1_767_225_602_000_000_000
    assert batch.logs[-1].body_bytes == 3
    assert severity_group(25) == "UNSPECIFIED"


def test_traces_use_status_kind_duration_and_exception_semantics(
    fixture_raw_root, fixture_run_id
) -> None:
    run = load_manifest(fixture_raw_root, fixture_run_id)
    batch = normalize_record(next(iter_signal_records(run, "traces")))
    assert batch.spans[0].is_error is True
    assert batch.spans[0].span_kind == "SERVER"
    assert batch.spans[0].duration_ms == 100.0
    assert batch.spans[0].exception_event_count == 1
    assert batch.spans[2].invalid_duration is True
    assert batch.spans[2].duration_ms is None
