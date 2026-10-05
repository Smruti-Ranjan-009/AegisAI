from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any

from confluent_kafka import KafkaError, Producer

from .config import KafkaSettings
from .errors import TransientPipelineError


class AcknowledgedProducer:
    def __init__(self, settings: KafkaSettings, client_id: str) -> None:
        self._producer = Producer(settings.producer_config(client_id))
        self._delivery_timeout = settings.delivery_timeout_ms / 1000

    def publish(
        self,
        topic: str,
        value: bytes | dict[str, Any],
        *,
        key: str | None = None,
        headers: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        payload = (
            json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
            if isinstance(value, dict)
            else value
        )
        outcome: list[KafkaError | None] = []

        def delivered(error: KafkaError | None, _message: object) -> None:
            outcome.append(error)

        try:
            self._producer.produce(
                topic,
                value=payload,
                key=key.encode() if key else None,
                headers=list(headers or []),
                on_delivery=delivered,
            )
        except BufferError as exc:
            raise TransientPipelineError(f"Kafka producer queue is full: {exc}") from exc

        deadline = time.monotonic() + self._delivery_timeout
        while not outcome and time.monotonic() < deadline:
            self._producer.poll(0.1)
        if not outcome:
            raise TransientPipelineError("Kafka delivery acknowledgement timed out")
        if outcome[0] is not None:
            raise TransientPipelineError(f"Kafka delivery failed: {outcome[0]}")

    def flush(self) -> None:
        remaining = self._producer.flush(self._delivery_timeout)
        if remaining:
            raise TransientPipelineError(
                f"Kafka producer still has {remaining} undelivered message(s)"
            )
