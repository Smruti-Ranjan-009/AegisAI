from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RANDOM_STATE = 42
TOP_K = 3
MIN_RUNS_PER_CLASS = 6
TEST_RUNS_PER_CLASS = 2
CV_SPLITS = 4
FEATURE_SCHEMA_VERSION = 1
FROZEN_ANOMALY_MODEL_ID = "anomaly-v1-4c84405c580f"
CLASS_NAMES = (
    "cpu_saturation",
    "memory_leak",
    "service_failure",
    "dependency_failure",
    "high_latency",
)
FORBIDDEN_FEATURE_FRAGMENTS = (
    "scenario",
    "label",
    "run_id",
    "service_name",
    "expected_service",
    "expected_affected",
    "is_injected_fault_service",
    "run_has_fault",
    "is_anomaly",
    "feature_flag",
    "fault_flag",
    "capture_path",
    "filename",
    "window_id",
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class AggregationConfig:
    top_k: int = TOP_K


@dataclass(frozen=True)
class TrainingConfig:
    random_state: int = RANDOM_STATE
    cv_splits: int = CV_SPLITS
    logistic_max_iter: int = 2000
    forest_estimators: int = 300
    forest_max_depth: int = 5
    forest_min_samples_leaf: int = 2
    practical_tie_tolerance: float = 0.01
