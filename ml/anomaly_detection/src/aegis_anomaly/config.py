from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RANDOM_STATE = 42
TARGET_NORMAL_FPR = 0.05
MIN_NORMAL_RUNS = 6
MIN_FAULT_RUNS = 2
MIN_NORMAL_WINDOWS = 150
MIN_SERVICE_NORMAL_WINDOWS = 5
FAULT_SCENARIOS = (
    "cpu_saturation",
    "memory_leak",
    "service_failure",
    "dependency_failure",
    "high_latency",
)
EXCLUDED_SERVICES = frozenset(
    {"__unknown__", "flagd", "load-generator", "otelcol-contrib", "telemetry-docs"}
)
METRIC_FEATURE_NAMES = (
    "metric_baseline_count",
    "metric_missing_baseline_count",
    "metric_coverage_ratio",
    "metric_abs_deviation_mean",
    "metric_abs_deviation_max",
    "metric_abs_deviation_p95",
    "metric_deviation_over_3_count",
    "metric_deviation_over_5_count",
)
FORBIDDEN_FEATURE_NAMES = frozenset(
    {
        "window_id",
        "metric_window_id",
        "run_id",
        "scenario",
        "label",
        "is_anomaly",
        "run_has_fault",
        "is_injected_fault_service",
        "service_name",
        "window_start_utc",
        "window_end_utc",
        "window_start",
        "window_end",
        "dataset_id",
        "capture_path",
        "feature_flag",
    }
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ReadinessRequirements:
    normal_runs: int = MIN_NORMAL_RUNS
    fault_runs_per_scenario: int = MIN_FAULT_RUNS
    normal_service_windows: int = MIN_NORMAL_WINDOWS


@dataclass(frozen=True)
class DetectorConfig:
    robust_top_k: int = 5
    isolation_estimators: int = 300
    random_state: int = RANDOM_STATE
    target_normal_fpr: float = TARGET_NORMAL_FPR
