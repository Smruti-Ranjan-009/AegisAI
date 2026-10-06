from datetime import UTC, datetime

from aegis_features.windows import (
    NANOSECONDS_PER_SECOND,
    service_window_id,
    window_bounds,
    window_start_ns,
)


def test_tumbling_window_boundaries_are_start_inclusive_end_exclusive() -> None:
    width = 60 * NANOSECONDS_PER_SECOND
    start = 1_767_225_600 * NANOSECONDS_PER_SECOND
    assert window_start_ns(start, 60) == start
    assert window_start_ns(start + width - 1, 60) == start
    assert window_start_ns(start + width, 60) == start + width


def test_window_bounds_are_utc() -> None:
    timestamp = 1_767_225_601 * NANOSECONDS_PER_SECOND
    start, end = window_bounds(timestamp, 60)
    assert start == datetime(2026, 1, 1, tzinfo=UTC)
    assert end == datetime(2026, 1, 1, 0, 1, tzinfo=UTC)


def test_window_identity_is_deterministic_and_isolates_run_and_service() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = service_window_id("run-a", "checkout", start, 60)
    assert first == service_window_id("run-a", "checkout", start, 60)
    assert first != service_window_id("run-b", "checkout", start, 60)
    assert first != service_window_id("run-a", "payment", start, 60)
