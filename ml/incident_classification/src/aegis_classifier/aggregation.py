from __future__ import annotations

from collections import defaultdict

import numpy as np

from .anomaly_adapter import ScoredWindow
from .config import CLASS_NAMES, AggregationConfig
from .errors import ClassificationError


def _values(rows: list[ScoredWindow], name: str) -> np.ndarray:
    values = np.asarray([row.features[name] for row in rows], dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ClassificationError(f"Aggregation input {name} contains non-finite values.")
    return values


def _mean(rows: list[ScoredWindow], name: str) -> float:
    return float(np.mean(_values(rows, name)))


def _maximum(rows: list[ScoredWindow], name: str) -> float:
    return float(np.max(_values(rows, name)))


def _sum(rows: list[ScoredWindow], name: str) -> float:
    return float(np.sum(_values(rows, name)))


def aggregate_run(rows: list[ScoredWindow], config: AggregationConfig) -> dict[str, object]:
    if not rows:
        raise ClassificationError("Cannot aggregate an empty incident run.")
    scenarios = {row.scenario for row in rows}
    run_ids = {row.run_id for row in rows}
    if len(run_ids) != 1 or len(scenarios) != 1:
        raise ClassificationError("Run aggregation received mixed run/scenario rows.")
    scenario = next(iter(scenarios))
    if scenario not in CLASS_NAMES:
        raise ClassificationError(f"Classifier dataset cannot contain scenario {scenario!r}.")
    ranked = sorted(
        rows,
        key=lambda row: (
            -row.anomaly_score,
            str(row.window_start_utc),
            row.service_name,
            row.window_id,
        ),
    )
    top = ranked[: min(config.top_k, len(ranked))]
    scores = np.asarray([row.anomaly_score for row in top], dtype=np.float64)
    output: dict[str, object] = {
        "run_id": next(iter(run_ids)),
        "scenario": scenario,
        "anomaly_score_max": float(scores.max()),
        "anomaly_score_mean_top3": float(scores.mean()),
        "anomaly_score_min_top3": float(scores.min()),
        "anomaly_score_std_top3": float(scores.std()),
        "anomaly_threshold_exceed_count": float(sum(row.anomaly_decision for row in rows)),
        "eligible_window_count": float(len(rows)),
        "metric_abs_deviation_mean_top3_mean": _mean(
            top, "metric_abs_deviation_mean"
        ),
        "metric_abs_deviation_mean_top3_max": _maximum(
            top, "metric_abs_deviation_mean"
        ),
        "metric_abs_deviation_max_top3_max": _maximum(top, "metric_abs_deviation_max"),
        "metric_abs_deviation_p95_top3_max": _maximum(top, "metric_abs_deviation_p95"),
        "metric_deviation_over_3_top3_sum": _sum(top, "metric_deviation_over_3_count"),
        "metric_deviation_over_5_top3_sum": _sum(top, "metric_deviation_over_5_count"),
        "metric_coverage_ratio_top3_mean": _mean(top, "metric_coverage_ratio"),
        "metric_missing_baseline_top3_sum": _sum(
            top, "metric_missing_baseline_count"
        ),
        "log_count_top3_sum": _sum(top, "log_count"),
        "log_warn_rate_top3_mean": _mean(top, "log_warn_rate"),
        "log_warn_rate_top3_max": _maximum(top, "log_warn_rate"),
        "log_error_rate_top3_mean": _mean(top, "log_error_rate"),
        "log_error_rate_top3_max": _maximum(top, "log_error_rate"),
        "log_fatal_rate_top3_max": _maximum(top, "log_fatal_rate"),
        "span_count_top3_sum": _sum(top, "span_count"),
        "span_error_rate_top3_mean": _mean(top, "span_error_rate"),
        "span_error_rate_top3_max": _maximum(top, "span_error_rate"),
        "span_duration_ms_mean_top3_mean": _mean(top, "span_duration_ms_mean"),
        "span_duration_ms_p95_top3_max": _maximum(top, "span_duration_ms_p95"),
        "span_duration_ms_p99_top3_max": _maximum(top, "span_duration_ms_p99"),
        "span_exception_event_count_top3_sum": _sum(top, "span_exception_event_count"),
        "metric_point_count_top3_sum": _sum(top, "metric_point_count"),
        "metric_name_count_top3_mean": _mean(top, "metric_name_count"),
        "telemetry_observation_count_top3_sum": _sum(
            top, "telemetry_observation_count"
        ),
    }
    numeric = [float(value) for key, value in output.items() if key not in {"run_id", "scenario"}]
    if not np.all(np.isfinite(numeric)):
        raise ClassificationError("Run aggregation produced a non-finite feature.")
    return output


def aggregate_runs(
    scored_windows: list[ScoredWindow], config: AggregationConfig | None = None
) -> list[dict[str, object]]:
    config = config or AggregationConfig()
    if config.top_k < 1:
        raise ClassificationError("top_k must be positive.")
    grouped: defaultdict[str, list[ScoredWindow]] = defaultdict(list)
    for row in scored_windows:
        grouped[row.run_id].append(row)
    return [aggregate_run(grouped[run_id], config) for run_id in sorted(grouped)]
