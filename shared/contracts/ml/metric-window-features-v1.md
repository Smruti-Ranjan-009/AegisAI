# Metric-window features v1

Schema version `1` is immutable. Each row is keyed by run, service, UTC window,
metric name, unit, and OTLP metric type. This long representation prevents
unrelated units or metric names from being averaged together.

## Field roles

- Metadata: `feature_schema_version`, `metric_window_id`, `run_id`,
  `service_name`, `window_start_utc`, `window_end_utc`, `window_seconds`,
  `metric_name`, `unit`, `metric_type`.
- Targets: `scenario`, `label`, `is_anomaly`.
- Predictive features: the ordered metric feature list in
  `ml/feature_engineering/feature_catalog_v1.json`.

Gauge and Sum rows expose point/series count plus value mean, population standard
deviation, min, max, linear-interpolated p50/p95/p99, first, and last. Counter
rates are deliberately absent in v1.

Histogram and ExponentialHistogram rows expose datapoint count, provided
observation count/sum/mean, and provided min/max. No percentile is invented from
incomplete buckets. Summary rows expose datapoint count, observation count, sum,
and mean. Statistics that do not apply to a metric type are nullable; counts are
non-null structural zero.
