package com.aegisai.incident.service;

import java.util.List;

public final class FrozenFeatureContract {
    public static final List<String> FEATURE_NAMES = List.of(
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
            "metric_baseline_count", "metric_missing_baseline_count", "metric_coverage_ratio",
            "metric_abs_deviation_mean", "metric_abs_deviation_max",
            "metric_abs_deviation_p95", "metric_deviation_over_3_count",
            "metric_deviation_over_5_count");

    private FrozenFeatureContract() {
    }
}
