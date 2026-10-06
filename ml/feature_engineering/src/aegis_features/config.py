from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FEATURE_SCHEMA_VERSION = 1
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_INVALID_OBSERVATION_RATIO = 0.01
UNKNOWN_SERVICE = "__unknown__"
KNOWN_SCENARIOS = frozenset(
    {
        "normal",
        "cpu_saturation",
        "memory_leak",
        "service_failure",
        "dependency_failure",
        "high_latency",
    }
)


@dataclass(frozen=True)
class BuildConfig:
    raw_root: Path
    output_root: Path
    window_seconds: int = DEFAULT_WINDOW_SECONDS
    max_invalid_observation_ratio: float = DEFAULT_MAX_INVALID_OBSERVATION_RATIO

    def __post_init__(self) -> None:
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if not 0 <= self.max_invalid_observation_ratio <= 1:
            raise ValueError("max_invalid_observation_ratio must be between 0 and 1")
