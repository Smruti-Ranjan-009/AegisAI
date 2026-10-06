from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from .config import FEATURE_SCHEMA_VERSION

NANOSECONDS_PER_SECOND = 1_000_000_000


def window_start_ns(timestamp_ns: int, window_seconds: int) -> int:
    if timestamp_ns < 0:
        raise ValueError("timestamp_ns must be non-negative")
    width = window_seconds * NANOSECONDS_PER_SECOND
    return timestamp_ns // width * width


def ns_to_utc(timestamp_ns: int) -> datetime:
    seconds, nanoseconds = divmod(timestamp_ns, NANOSECONDS_PER_SECOND)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=nanoseconds // 1_000)


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def window_bounds(timestamp_ns: int, window_seconds: int) -> tuple[datetime, datetime]:
    start = ns_to_utc(window_start_ns(timestamp_ns, window_seconds))
    return start, start + timedelta(seconds=window_seconds)


def stable_id(*parts: object) -> str:
    canonical = "|".join(str(part) for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def service_window_id(
    run_id: str, service_name: str, window_start: datetime, window_seconds: int
) -> str:
    return stable_id(
        f"v{FEATURE_SCHEMA_VERSION}",
        run_id,
        service_name,
        utc_text(window_start),
        window_seconds,
    )


def metric_window_id(
    run_id: str,
    service_name: str,
    window_start: datetime,
    window_seconds: int,
    metric_name: str,
    unit: str,
    metric_type: str,
) -> str:
    return stable_id(
        f"v{FEATURE_SCHEMA_VERSION}",
        run_id,
        service_name,
        utc_text(window_start),
        window_seconds,
        metric_name,
        unit,
        metric_type,
    )
