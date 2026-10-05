from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from .errors import TransientPipelineError

T = TypeVar("T")


def with_retry(
    operation: Callable[[], T],
    *,
    max_attempts: int,
    initial_seconds: float,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    for attempt in range(1, max_attempts + 1):
        try:
            return operation(), attempt
        except TransientPipelineError:
            if attempt == max_attempts:
                raise
            sleeper(initial_seconds * (2 ** (attempt - 1)))
    raise AssertionError("retry loop exhausted unexpectedly")
