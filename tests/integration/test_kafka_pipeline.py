from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from confluent_kafka import Consumer, KafkaError, KafkaException

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services/telemetry-service"))

from app.messaging.admin import provision_topics, topic_status  # noqa: E402
from app.messaging.config import KafkaSettings, load_topic_specs  # noqa: E402
from app.messaging.contracts import kafka_headers  # noqa: E402
from app.messaging.producer import AcknowledgedProducer  # noqa: E402

pytestmark = [
    pytest.mark.kafka_integration,
    pytest.mark.skipif(
        os.getenv("KAFKA_INTEGRATION") != "1",
        reason="set KAFKA_INTEGRATION=1 to run real Kafka tests",
    ),
]

FIXTURES = REPO_ROOT / "services/telemetry-service/tests/fixtures"


def _headers(signal: str | None, run_id: str) -> list[tuple[str, str]]:
    result = [
        ("aegis.event_type", "telemetry.raw"),
        ("aegis.schema_version", "1"),
        ("aegis.run_id", run_id),
        ("aegis.scenario", "integration"),
        ("aegis.label", "integration"),
    ]
    if signal is not None:
        result.append(("aegis.signal", signal))
    return result


def _read_matching(
    settings: KafkaSettings,
    topic: str,
    run_id: str,
    count: int,
    timeout: float = 45,
) -> list[dict[str, Any]]:
    config = settings.consumer_config(f"integration-inspect-{uuid.uuid4()}")
    consumer = Consumer(config)
    found: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    consumer.subscribe([topic])
    try:
        while len(found) < count and time.monotonic() < deadline:
            message = consumer.poll(0.5)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(message.error())
            value = json.loads(message.value().decode())
            if value.get("ground_truth", {}).get("run_id") == run_id:
                found.append(
                    {
                        "value": value,
                        "headers": kafka_headers(message.headers()),
                        "key": message.key().decode() if message.key() else None,
                    }
                )
    finally:
        consumer.close()
    assert len(found) == count, f"received {len(found)} matching {topic} records, expected {count}"
    return found


def test_topic_provisioning_is_idempotent() -> None:
    settings = KafkaSettings.from_environment()
    specs = load_topic_specs()
    provision_topics(settings, specs)
    provision_topics(settings, specs)
    status = topic_status(settings, specs)
    assert [(item["topic"], item["partitions"]) for item in status] == [
        ("telemetry.raw", 3),
        ("telemetry.processed", 3),
        ("telemetry.dlq", 1),
    ]


def test_valid_raw_processed_and_malformed_records_reach_dlq() -> None:
    settings = KafkaSettings.from_environment()
    producer = AcknowledgedProducer(settings, "aegis-integration-test")
    valid_run = f"integration-valid-{uuid.uuid4()}"
    for signal in ("metrics", "logs", "traces"):
        producer.publish(
            settings.raw_topic,
            (FIXTURES / f"{signal}.json").read_bytes(),
            key=valid_run,
            headers=_headers(signal, valid_run),
        )

    processed = _read_matching(settings, settings.processed_topic, valid_run, 3)
    assert {item["value"]["signal"] for item in processed} == {"metrics", "logs", "traces"}
    assert {item["value"]["ground_truth"]["label"] for item in processed} == {
        "integration"
    }
    assert all(item["headers"]["aegis.event_type"] == "telemetry.processed" for item in processed)
    assert {name for item in processed for name in item["value"]["service_names"]} == {
        "checkout",
        "payment",
        "frontend",
    }

    invalid_run = f"integration-invalid-{uuid.uuid4()}"
    producer.publish(
        settings.raw_topic,
        b"not-json",
        key=invalid_run,
        headers=_headers("metrics", invalid_run),
    )
    producer.publish(
        settings.raw_topic,
        b"{}",
        key=invalid_run,
        headers=_headers(None, invalid_run),
    )
    producer.publish(
        settings.raw_topic,
        b"{}",
        key=invalid_run,
        headers=_headers("profiles", invalid_run),
    )
    dlq = _read_matching(settings, settings.dlq_topic, invalid_run, 3)
    assert {item["value"]["error"]["category"] for item in dlq} == {
        "invalid_json",
        "missing_header",
        "unsupported_signal",
    }

    recovery_run = f"integration-recovery-{uuid.uuid4()}"
    producer.publish(
        settings.raw_topic,
        (FIXTURES / "metrics.json").read_bytes(),
        key=recovery_run,
        headers=_headers("metrics", recovery_run),
    )
    recovered = _read_matching(settings, settings.processed_topic, recovery_run, 1)
    assert recovered[0]["value"]["service_names"] == ["checkout"]
    producer.flush()
