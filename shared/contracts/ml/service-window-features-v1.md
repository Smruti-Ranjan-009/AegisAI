# Service-window features v1

Schema version `1` is immutable. Meaning-changing revisions require v2.

Each row represents one Phase 1 run, resource-level service, and UTC tumbling
window. Rows are sorted by `run_id`, `window_start_utc`, then `service_name`.

## Field roles

- Metadata: `feature_schema_version`, `window_id`, `run_id`, `service_name`,
  `window_start_utc`, `window_end_utc`, `window_seconds`, `source_event_count`.
- Targets: `scenario`, `label`, `is_anomaly`.
- Predictive features: the ordered service feature list in
  `ml/feature_engineering/feature_catalog_v1.json`.

`window_id` is SHA-256 over schema version, run ID, service, UTC window start,
and window duration. Target and metadata fields are prohibited from the feature
list.

## Feature groups

- Log counts by OTLP severity group, WARN/ERROR/FATAL rates, and UTF-8/body byte
  size mean/max.
- Span count/error rate, non-negative duration mean/min/max/p50/p95/p99, OTLP
  kind counts, unique operation count, and exception event count.
- Metric name/point/type counts and total telemetry observation count.

Counts/rates use structural zero when a signal is absent. Log body and span
duration statistics are nullable when no valid observation exists. Durations
are milliseconds; rates are unitless `[0, 1]`; timestamps are UTC.
