from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SERVICE_FEATURES = (
    "log_count", "log_trace_count", "log_debug_count", "log_info_count",
    "log_warn_count", "log_error_count", "log_fatal_count", "log_unspecified_count",
    "log_warn_rate", "log_error_rate", "log_fatal_rate", "log_body_bytes_mean",
    "log_body_bytes_max", "span_count", "span_error_count", "span_error_rate",
    "span_duration_ms_mean", "span_duration_ms_min", "span_duration_ms_max",
    "span_duration_ms_p50", "span_duration_ms_p95", "span_duration_ms_p99",
    "span_internal_count", "span_server_count", "span_client_count",
    "span_producer_count", "span_consumer_count", "span_unspecified_count",
    "span_unique_operation_count", "span_exception_event_count", "metric_name_count",
    "metric_point_count", "metric_gauge_count", "metric_sum_count",
    "metric_histogram_count", "metric_exponential_histogram_count",
    "metric_summary_count", "telemetry_observation_count",
)
METRIC_FEATURES = (
    "metric_baseline_count", "metric_missing_baseline_count", "metric_coverage_ratio",
    "metric_abs_deviation_mean", "metric_abs_deviation_max",
    "metric_abs_deviation_p95", "metric_deviation_over_3_count",
    "metric_deviation_over_5_count",
)
FEATURE_NAMES = SERVICE_FEATURES + METRIC_FEATURES
CLASS_NAMES = (
    "cpu_saturation", "memory_leak", "service_failure",
    "dependency_failure", "high_latency",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


FiniteValue = Annotated[float | None, Field(strict=True)]


class FeatureWindow(StrictModel):
    window_id: str = Field(min_length=1, max_length=200)
    service_name: str = Field(min_length=1, max_length=200)
    window_start_utc: datetime
    window_end_utc: datetime
    values: list[FiniteValue]

    @field_validator("values")
    @classmethod
    def finite_values(cls, values: list[float | None]) -> list[float | None]:
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("feature values must be finite or null")
        return values

    @model_validator(mode="after")
    def valid_window(self) -> FeatureWindow:
        if self.window_end_utc <= self.window_start_utc:
            raise ValueError("window_end_utc must be after window_start_utc")
        return self


class InferenceRequest(StrictModel):
    schema_version: Literal["ml_inference_v1"]
    feature_schema_version: Literal[1]
    input_id: str = Field(min_length=1, max_length=200)
    feature_names: list[str]
    windows: list[FeatureWindow] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def frozen_contract(self) -> InferenceRequest:
        if tuple(self.feature_names) != FEATURE_NAMES:
            raise ValueError("feature_names must exactly match the frozen Phase 5 ordering")
        if any(len(window.values) != len(FEATURE_NAMES) for window in self.windows):
            raise ValueError("every window must contain exactly 46 feature values")
        if len({window.window_id for window in self.windows}) != len(self.windows):
            raise ValueError("window_id values must be unique")
        return self


class ModelIdentity(StrictModel):
    name: str
    model_id: str
    source: str
    artifact_sha256: str | None = None
    registry_uri: str | None = None


class WindowScore(StrictModel):
    window_id: str
    service_name: str
    anomaly_score: float
    is_anomaly: bool


class AnomalyResult(StrictModel):
    model: ModelIdentity
    threshold: float
    score: float
    is_anomaly: bool
    windows: list[WindowScore]


class ClassificationResult(StrictModel):
    model: ModelIdentity
    predicted_incident_type: Literal[
        "cpu_saturation", "memory_leak", "service_failure",
        "dependency_failure", "high_latency"
    ]
    class_probabilities: dict[str, float]


class InferenceResponse(StrictModel):
    schema_version: Literal["ml_inference_result_v1"] = "ml_inference_result_v1"
    input_id: str
    analysis_status: Literal["anomaly_detected", "no_anomaly_signal"]
    anomaly: AnomalyResult
    classification: ClassificationResult | None
    lineage: dict[str, object]
    timings_ms: dict[str, float]
    correlation_id: str
