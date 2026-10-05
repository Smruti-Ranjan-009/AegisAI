from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.messaging.config import KafkaSettings, load_topic_specs, topics_file
from app.messaging.contracts import (
    build_processed_event,
    decode_otlp,
    deterministic_event_id,
    extract_service_names,
    kafka_headers,
    validate_raw_headers,
    validate_schema,
)
from app.messaging.dlq import build_dlq_event
from app.messaging.errors import (
    PermanentMessageError,
    TransientPipelineError,
    is_permanent_category,
)
from app.messaging.processor import process_record
from app.messaging.replay import load_replay_manifest, replay_capture
from app.messaging.retry import with_retry

FIXTURES = Path(__file__).parent / "fixtures"


class FakeMessage:
    def __init__(
        self,
        value: bytes,
        headers: list[tuple[str, bytes | None]],
        *,
        partition: int = 1,
        offset: int = 42,
    ) -> None:
        self._value = value
        self._headers = headers
        self._partition = partition
        self._offset = offset

    def topic(self) -> str:
        return "telemetry.raw"

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset

    def value(self) -> bytes:
        return self._value

    def headers(self) -> list[tuple[str, bytes | None]]:
        return self._headers


class FakeProducer:
    def __init__(self) -> None:
        self.records: list[tuple[str, bytes | dict[str, object], str | None, object]] = []
        self.flushed = False

    def publish(
        self,
        topic: str,
        value: bytes | dict[str, object],
        *,
        key: str | None = None,
        headers: object = None,
    ) -> None:
        self.records.append((topic, value, key, headers))

    def flush(self) -> None:
        self.flushed = True


def raw_headers(signal: str = "metrics") -> list[tuple[str, bytes]]:
    return [
        ("aegis.event_type", b"telemetry.raw"),
        ("aegis.schema_version", b"1"),
        ("aegis.signal", signal.encode()),
    ]


def fixture(signal: str) -> bytes:
    return (FIXTURES / f"{signal}.json").read_bytes()


def test_kafka_configuration_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "broker:19092")
    monkeypatch.setenv("KAFKA_PROCESSING_MAX_ATTEMPTS", "4")
    settings = KafkaSettings.from_environment()
    assert settings.bootstrap_servers == "broker:19092"
    assert settings.max_attempts == 4
    assert settings.producer_config("test")["enable.idempotence"] is True
    assert settings.consumer_config()["enable.auto.commit"] is False
    specs = load_topic_specs()
    assert [(spec.name, spec.partitions) for spec in specs] == [
        ("telemetry.raw", 3),
        ("telemetry.processed", 3),
        ("telemetry.dlq", 1),
    ]
    configured_path = Path("/container/topics.json")
    monkeypatch.setenv("AEGIS_KAFKA_TOPICS_FILE", str(configured_path))
    assert topics_file() == configured_path


def test_required_headers_and_signal_parsing() -> None:
    headers = kafka_headers(raw_headers("logs"))
    assert validate_raw_headers(headers) == "logs"
    with pytest.raises(PermanentMessageError, match="Missing required") as missing:
        validate_raw_headers({})
    assert missing.value.category == "missing_header"
    with pytest.raises(PermanentMessageError) as unsupported:
        validate_raw_headers(kafka_headers(raw_headers("profiles")))
    assert unsupported.value.category == "unsupported_signal"


@pytest.mark.parametrize(
    ("signal", "service"),
    [("metrics", "checkout"), ("logs", "payment"), ("traces", "frontend")],
)
def test_otlp_validation_and_service_extraction(signal: str, service: str) -> None:
    payload = decode_otlp(fixture(signal), signal)
    assert extract_service_names(payload, signal) == (service,)


@pytest.mark.parametrize("signal", ["metrics", "logs", "traces"])
def test_empty_otlp_export_request_is_valid(signal: str) -> None:
    payload = decode_otlp(b"{}", signal)
    assert payload == {
        {"metrics": "resourceMetrics", "logs": "resourceLogs", "traces": "resourceSpans"}[
            signal
        ]: []
    }


def test_malformed_otlp_signal_root_is_rejected() -> None:
    with pytest.raises(PermanentMessageError) as invalid:
        decode_otlp(b'{"resourceMetrics": {}}', "metrics")
    assert invalid.value.category == "invalid_otlp_structure"


def test_deterministic_event_id_and_processed_event_schema() -> None:
    first = deterministic_event_id("telemetry.raw", 1, 42)
    assert first == deterministic_event_id("telemetry.raw", 1, 42)
    assert first != deterministic_event_id("telemetry.raw", 1, 43)
    event = build_processed_event(
        topic="telemetry.raw",
        partition=1,
        offset=42,
        signal="metrics",
        headers={"aegis.run_id": "run", "aegis.scenario": "normal", "aegis.label": "normal"},
        payload=decode_otlp(fixture("metrics"), "metrics"),
    )
    validate_schema(event, "telemetry-processed-v1.schema.json")
    assert event["event_id"] == first
    assert event["service_names"] == ["checkout"]
    assert event["ground_truth"]["run_id"] == "run"


def test_process_record_uses_service_key_and_fallback_event_id() -> None:
    processed = process_record(FakeMessage(fixture("metrics"), raw_headers()))
    assert processed.key == "checkout"
    no_service = json.dumps({"resourceMetrics": [{"resource": {}}]}).encode()
    fallback = process_record(FakeMessage(no_service, raw_headers()))
    assert fallback.key == fallback.event["event_id"]


def test_dlq_envelope_and_error_classification() -> None:
    event = build_dlq_event(
        topic="telemetry.raw",
        partition=0,
        offset=7,
        headers={"aegis.signal": "metrics", "aegis.run_id": "run-1"},
        payload=b"not json",
        category="invalid_json",
        message="bad input",
        attempts=1,
    )
    validate_schema(event, "telemetry-dlq-v1.schema.json")
    assert event["error"]["category"] == "invalid_json"
    assert is_permanent_category("invalid_json")
    assert not is_permanent_category("processing_error")


def test_retry_uses_exponential_backoff_without_sleeping() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientPipelineError("temporary")
        return "ok"

    result, used = with_retry(
        operation, max_attempts=3, initial_seconds=0.25, sleeper=sleeps.append
    )
    assert (result, used) == ("ok", 3)
    assert sleeps == [0.25, 0.5]


def test_replay_manifest_and_signal_mapping(tmp_path: Path) -> None:
    run_id = "20261005T153012Z-normal-a1b2c3"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario": "normal",
        "label": "normal",
        "signals": {signal: f"{signal}.jsonl" for signal in ("metrics", "logs", "traces")},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for signal in ("metrics", "logs", "traces"):
        (run_dir / f"{signal}.jsonl").write_bytes(fixture(signal) + b"\n")
    assert load_replay_manifest(run_dir)["run_id"] == run_id
    producer = FakeProducer()
    result = replay_capture(run_dir, KafkaSettings(), producer=producer)  # type: ignore[arg-type]
    assert result.counts == {"metrics": 1, "logs": 1, "traces": 1}
    assert producer.flushed
    signals = [dict(record[3])["aegis.signal"] for record in producer.records]
    assert signals == ["metrics", "logs", "traces"]


def test_invalid_replay_manifest_is_rejected(tmp_path: Path) -> None:
    run_dir = tmp_path / "wrong"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_replay_manifest(run_dir)
