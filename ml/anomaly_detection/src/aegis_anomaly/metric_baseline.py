from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import METRIC_FEATURE_NAMES, MIN_SERVICE_NORMAL_WINDOWS
from .errors import AnomalyError

SERVICE_WINDOW_KEY = tuple[str, str, Any]
BaselineKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class Baseline:
    median: float
    scale: float
    sample_count: int
    informative: bool


def _metric_value(row: dict[str, Any]) -> tuple[str, float] | None:
    metric_type = row["metric_type"]
    mapping = {
        "Gauge": "metric_value_mean",
        "Histogram": "histogram_mean",
        "ExponentialHistogram": "histogram_mean",
        "Summary": "summary_mean",
    }
    statistic = mapping.get(metric_type)
    if statistic is None:
        return None
    value = row.get(statistic)
    if value is None or not np.isfinite(float(value)):
        return None
    return statistic, float(value)


def _baseline(values: list[float]) -> Baseline:
    array = np.asarray(values, dtype=np.float64)
    median = float(np.median(array))
    mad_scale = float(np.median(np.abs(array - median)) * 1.4826)
    if mad_scale > 0 and np.isfinite(mad_scale):
        return Baseline(median, mad_scale, len(values), True)
    q25, q75 = np.quantile(array, [0.25, 0.75])
    iqr_scale = float((q75 - q25) / 1.349)
    if iqr_scale > 0 and np.isfinite(iqr_scale):
        return Baseline(median, iqr_scale, len(values), True)
    return Baseline(median, 1.0, len(values), False)


class MetricBaselineTransformer:
    def __init__(self, minimum_service_windows: int = MIN_SERVICE_NORMAL_WINDOWS) -> None:
        self.minimum_service_windows = minimum_service_windows
        self.service_baselines: dict[BaselineKey, Baseline] = {}
        self.global_baselines: dict[BaselineKey, Baseline] = {}
        self.service_window_counts: dict[str, int] = {}
        self.fit_run_ids: tuple[str, ...] = ()

    def fit(
        self,
        metric_rows: list[dict[str, Any]],
        service_rows: list[dict[str, Any]],
        training_run_ids: set[str],
        eligible_services: set[str],
    ) -> MetricBaselineTransformer:
        if any(
            row["run_id"] in training_run_ids and row["scenario"] != "normal"
            for row in service_rows
        ):
            raise AnomalyError("Metric baseline training runs include a fault scenario.")
        window_counts = Counter(
            row["service_name"]
            for row in service_rows
            if row["run_id"] in training_run_ids
            and row["scenario"] == "normal"
            and row["service_name"] in eligible_services
        )
        service_values: defaultdict[BaselineKey, list[float]] = defaultdict(list)
        global_values: defaultdict[BaselineKey, list[float]] = defaultdict(list)
        for row in metric_rows:
            if (
                row["run_id"] not in training_run_ids
                or row["scenario"] != "normal"
                or row["service_name"] not in eligible_services
            ):
                continue
            selected = _metric_value(row)
            if selected is None:
                continue
            statistic, value = selected
            semantic = (row["metric_name"], row["unit"], row["metric_type"], statistic)
            global_values[semantic].append(value)
            if window_counts[row["service_name"]] >= self.minimum_service_windows:
                service_values[(row["service_name"], *semantic)].append(value)
        self.service_baselines = {key: _baseline(values) for key, values in service_values.items()}
        self.global_baselines = {key: _baseline(values) for key, values in global_values.items()}
        self.service_window_counts = {
            service: int(window_counts[service]) for service in sorted(eligible_services)
        }
        self.fit_run_ids = tuple(sorted(training_run_ids))
        return self

    def transform(
        self,
        metric_rows: list[dict[str, Any]],
        service_rows: list[dict[str, Any]],
    ) -> dict[SERVICE_WINDOW_KEY, dict[str, float]]:
        if not self.fit_run_ids:
            raise AnomalyError("Metric baseline transformer must be fitted before transform.")
        deviations: defaultdict[SERVICE_WINDOW_KEY, list[float]] = defaultdict(list)
        missing: Counter[SERVICE_WINDOW_KEY] = Counter()
        candidates: Counter[SERVICE_WINDOW_KEY] = Counter()
        for row in metric_rows:
            selected = _metric_value(row)
            if selected is None:
                continue
            statistic, value = selected
            window_key = (row["run_id"], row["service_name"], row["window_start_utc"])
            candidates[window_key] += 1
            semantic = (row["metric_name"], row["unit"], row["metric_type"], statistic)
            baseline = self.service_baselines.get((row["service_name"], *semantic))
            if baseline is None:
                baseline = self.global_baselines.get(semantic)
            if baseline is None:
                missing[window_key] += 1
                continue
            deviation = abs(value - baseline.median) / baseline.scale
            deviations[window_key].append(float(deviation if baseline.informative else 0.0))

        result: dict[SERVICE_WINDOW_KEY, dict[str, float]] = {}
        for row in service_rows:
            key = (row["run_id"], row["service_name"], row["window_start_utc"])
            values = np.asarray(deviations[key], dtype=np.float64)
            matched = len(values)
            total = candidates[key]
            absent = missing[key]
            result[key] = {
                "metric_baseline_count": float(matched),
                "metric_missing_baseline_count": float(absent),
                "metric_coverage_ratio": float(matched / total) if total else 0.0,
                "metric_abs_deviation_mean": float(values.mean()) if matched else 0.0,
                "metric_abs_deviation_max": float(values.max()) if matched else 0.0,
                "metric_abs_deviation_p95": (
                    float(np.quantile(values, 0.95)) if matched else 0.0
                ),
                "metric_deviation_over_3_count": float(np.sum(values > 3.0)),
                "metric_deviation_over_5_count": float(np.sum(values > 5.0)),
            }
        return result

    @staticmethod
    def feature_names() -> tuple[str, ...]:
        return METRIC_FEATURE_NAMES
