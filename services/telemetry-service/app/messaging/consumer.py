from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from .config import KafkaSettings
from .contracts import deterministic_event_id, kafka_headers, validate_schema
from .dlq import build_dlq_event
from .errors import PermanentMessageError, TransientPipelineError
from .processor import process_record
from .producer import AcknowledgedProducer
from .retry import with_retry

LOGGER = logging.getLogger("aegis.telemetry.worker")


def _log(event: str, **fields: object) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, separators=(",", ":")))


def _safe_headers(message: Message) -> dict[str, str | None]:
    try:
        return kafka_headers(message.headers())
    except PermanentMessageError:
        result: dict[str, str | None] = {}
        for key, value in message.headers() or []:
            result[key] = value.decode("utf-8", errors="replace") if value else None
        return result


class TelemetryWorker:
    def __init__(
        self,
        settings: KafkaSettings,
        *,
        consumer: Consumer | None = None,
        producer: AcknowledgedProducer | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self.consumer = consumer or Consumer(settings.consumer_config())
        self.producer = producer or AcknowledgedProducer(settings, "aegis-telemetry-worker")
        self.sleeper = sleeper

    def _retry(self, operation: Callable[[], Any]) -> tuple[Any, int]:
        arguments: dict[str, Any] = {
            "max_attempts": self.settings.max_attempts,
            "initial_seconds": self.settings.retry_initial_seconds,
        }
        if self.sleeper is not None:
            arguments["sleeper"] = self.sleeper
        return with_retry(operation, **arguments)

    def _publish_dlq(
        self,
        message: Message,
        *,
        category: str,
        error_message: str,
        attempts: int,
    ) -> None:
        headers = _safe_headers(message)
        event = build_dlq_event(
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            headers=headers,
            payload=message.value() or b"",
            category=category,
            message=error_message,
            attempts=attempts,
        )
        validate_schema(event, "telemetry-dlq-v1.schema.json")
        key = deterministic_event_id(message.topic(), message.partition(), message.offset())
        self._retry(lambda: self.producer.publish(self.settings.dlq_topic, event, key=key))
        _log(
            "record_sent_to_dlq",
            category=category,
            partition=message.partition(),
            offset=message.offset(),
        )

    def handle(self, message: Message) -> str:
        attempts = 1
        try:
            processed = process_record(message)
            try:
                _, attempts = self._retry(
                    lambda: self.producer.publish(
                        self.settings.processed_topic,
                        processed.event,
                        key=processed.key,
                        headers=[
                            ("aegis.event_type", "telemetry.processed"),
                            ("aegis.schema_version", "1"),
                            ("aegis.signal", processed.event["signal"]),
                        ],
                    )
                )
            except TransientPipelineError as exc:
                self._publish_dlq(
                    message,
                    category="processing_error",
                    error_message=str(exc),
                    attempts=self.settings.max_attempts,
                )
                return "dlq"
        except PermanentMessageError as exc:
            self._publish_dlq(
                message,
                category=exc.category,
                error_message=str(exc),
                attempts=attempts,
            )
            return "dlq"
        except Exception as exc:
            self._publish_dlq(
                message,
                category="processing_error",
                error_message=str(exc),
                attempts=attempts,
            )
            return "dlq"
        _log(
            "record_processed",
            partition=message.partition(),
            offset=message.offset(),
            event_id=processed.event["event_id"],
        )
        return "processed"

    def run(self, stop_requested: Callable[[], bool]) -> None:
        self.consumer.subscribe(
            [self.settings.raw_topic],
            on_assign=lambda _consumer, partitions: _log(
                "partitions_assigned", partitions=[str(partition) for partition in partitions]
            ),
            on_revoke=lambda _consumer, partitions: _log(
                "partitions_revoked", partitions=[str(partition) for partition in partitions]
            ),
        )
        _log("consumer_started", group=self.settings.consumer_group)
        try:
            while not stop_requested():
                message = self.consumer.poll(1.0)
                if message is None:
                    continue
                if message.error():
                    if message.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(message.error())
                self.handle(message)
                self.consumer.commit(message=message, asynchronous=False)
        finally:
            try:
                self.producer.flush()
            finally:
                self.consumer.close()
            _log("consumer_stopped", group=self.settings.consumer_group)
