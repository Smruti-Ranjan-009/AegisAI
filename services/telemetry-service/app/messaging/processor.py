from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import (
    build_processed_event,
    decode_otlp,
    kafka_headers,
    validate_raw_headers,
    validate_schema,
)


class SourceRecord(Protocol):
    def topic(self) -> str: ...

    def partition(self) -> int: ...

    def offset(self) -> int: ...

    def value(self) -> bytes: ...

    def headers(self) -> list[tuple[str, bytes | None]] | None: ...


@dataclass(frozen=True)
class ProcessedRecord:
    event: dict[str, Any]
    key: str
    headers: dict[str, str | None]


def process_record(record: SourceRecord) -> ProcessedRecord:
    headers = kafka_headers(record.headers())
    signal = validate_raw_headers(headers)
    payload = decode_otlp(record.value(), signal)
    event = build_processed_event(
        topic=record.topic(),
        partition=record.partition(),
        offset=record.offset(),
        signal=signal,
        headers=headers,
        payload=payload,
    )
    validate_schema(event, "telemetry-processed-v1.schema.json")
    key = event["service_names"][0] if event["service_names"] else event["event_id"]
    return ProcessedRecord(event=event, key=key, headers=headers)
