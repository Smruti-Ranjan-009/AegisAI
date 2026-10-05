from __future__ import annotations

from test_messaging import FakeProducer

from app.messaging.config import KafkaSettings
from app.messaging.consumer import TelemetryWorker


class FakeConsumer:
    def __init__(self) -> None:
        self.subscriptions: list[str] = []
        self.closed = False

    def subscribe(self, topics: list[str], **_kwargs: object) -> None:
        self.subscriptions = topics

    def poll(self, _timeout: float) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_worker_graceful_cleanup_without_polling() -> None:
    consumer = FakeConsumer()
    producer = FakeProducer()
    worker = TelemetryWorker(
        KafkaSettings(),
        consumer=consumer,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
    )

    worker.run(lambda: True)

    assert consumer.subscriptions == ["telemetry.raw"]
    assert consumer.closed
    assert producer.flushed
