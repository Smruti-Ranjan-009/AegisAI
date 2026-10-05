from __future__ import annotations

import json
import time
import uuid
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException

from .config import KafkaSettings
from .contracts import kafka_headers


def consume_records(
    settings: KafkaSettings,
    topic: str,
    *,
    limit: int,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    config = settings.consumer_config(f"aegis-inspect-{uuid.uuid4()}")
    consumer = Consumer(config)
    records = []
    deadline = time.monotonic() + timeout_seconds
    consumer.subscribe([topic])
    try:
        while len(records) < limit and time.monotonic() < deadline:
            message = consumer.poll(0.5)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(message.error())
            payload = message.value().decode("utf-8")
            records.append(
                {
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "key": message.key().decode("utf-8") if message.key() else None,
                    "headers": kafka_headers(message.headers()),
                    "value": json.loads(payload),
                }
            )
    finally:
        consumer.close()
    return records
