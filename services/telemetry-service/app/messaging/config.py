from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class KafkaSettings:
    bootstrap_servers: str = "localhost:9092"
    raw_topic: str = "telemetry.raw"
    processed_topic: str = "telemetry.processed"
    dlq_topic: str = "telemetry.dlq"
    consumer_group: str = "aegis-telemetry-processor-v1"
    max_attempts: int = 3
    retry_initial_seconds: float = 0.5
    delivery_timeout_ms: int = 30_000

    @classmethod
    def from_environment(cls) -> KafkaSettings:
        settings = cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", cls.bootstrap_servers),
            raw_topic=os.getenv("KAFKA_RAW_TOPIC", cls.raw_topic),
            processed_topic=os.getenv("KAFKA_PROCESSED_TOPIC", cls.processed_topic),
            dlq_topic=os.getenv("KAFKA_DLQ_TOPIC", cls.dlq_topic),
            consumer_group=os.getenv("KAFKA_CONSUMER_GROUP", cls.consumer_group),
            max_attempts=int(os.getenv("KAFKA_PROCESSING_MAX_ATTEMPTS", cls.max_attempts)),
            retry_initial_seconds=float(
                os.getenv("KAFKA_RETRY_INITIAL_SECONDS", cls.retry_initial_seconds)
            ),
            delivery_timeout_ms=int(
                os.getenv("KAFKA_DELIVERY_TIMEOUT_MS", cls.delivery_timeout_ms)
            ),
        )
        if settings.max_attempts < 1:
            raise ValueError("KAFKA_PROCESSING_MAX_ATTEMPTS must be at least 1")
        if settings.retry_initial_seconds < 0:
            raise ValueError("KAFKA_RETRY_INITIAL_SECONDS cannot be negative")
        return settings

    def producer_config(self, client_id: str) -> dict[str, Any]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": client_id,
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "zstd",
            "delivery.timeout.ms": self.delivery_timeout_ms,
            "request.timeout.ms": min(self.delivery_timeout_ms, 10_000),
            "allow.auto.create.topics": False,
        }

    def consumer_config(self, group_id: str | None = None) -> dict[str, Any]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id or self.consumer_group,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            "allow.auto.create.topics": False,
        }


@dataclass(frozen=True)
class TopicSpec:
    name: str
    partitions: int
    replication_factor: int
    config: dict[str, str]


def topics_file() -> Path:
    configured = os.getenv("AEGIS_KAFKA_TOPICS_FILE")
    if configured:
        return Path(configured)
    return _repository_root() / "infrastructure/kafka/topics.json"


def load_topic_specs(path: Path | None = None) -> tuple[TopicSpec, ...]:
    document = json.loads((path or topics_file()).read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("topics"), list):
        raise ValueError("Kafka topics document must have schema_version 1 and a topics array")
    specs = tuple(
        TopicSpec(
            name=item["name"],
            partitions=int(item["partitions"]),
            replication_factor=int(item["replication_factor"]),
            config={str(key): str(value) for key, value in item["config"].items()},
        )
        for item in document["topics"]
    )
    names = [spec.name for spec in specs]
    if names != ["telemetry.raw", "telemetry.processed", "telemetry.dlq"]:
        raise ValueError("Phase 2 topic catalog must contain exactly the three active topics")
    return specs
