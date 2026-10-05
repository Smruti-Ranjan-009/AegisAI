from __future__ import annotations

import base64
from typing import Any

from .contracts import ground_truth, utc_timestamp


def build_dlq_event(
    *,
    topic: str,
    partition: int,
    offset: int,
    headers: dict[str, str | None],
    payload: bytes,
    category: str,
    message: str,
    attempts: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_type": "telemetry.dlq",
        "failed_at_utc": utc_timestamp(),
        "source": {"topic": topic, "partition": partition, "offset": offset},
        "headers": headers,
        "error": {"category": category, "message": message},
        "processing_attempt_count": attempts,
        "raw_payload": {
            "encoding": "base64",
            "data": base64.b64encode(payload).decode("ascii"),
        },
        "ground_truth": ground_truth(headers),
    }
