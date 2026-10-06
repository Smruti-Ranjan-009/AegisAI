# Phase 4 feature engineering

Phase 4 converts validated, labeled Phase 1 OTLP JSON captures into deterministic
model-ready Parquet tables. It is offline-only and performs no model training,
feature selection, scaling, fitted imputation, inference, or serving.

## Inputs and lineage

Each input is `data/raw/<run-id>/manifest.json` plus `metrics.jsonl`,
`logs.jsonl`, and `traces.jsonl`. Inputs are read-only. The loader validates the
manifest schema, safe/matching run ID, known scenario, matching label, signal
filenames, and non-empty files. A stored `validation_status`, when present, must
be `PASS`; legacy Phase 1 v1 manifests omit this field and instead pass the same
full structural validation on every build.

Every output manifest contains source run IDs, SHA-256 hashes and byte sizes.
Every row retains its `run_id`. Future train/validation/test splitting must group
by run ID; randomly splitting neighboring windows from one run would leak
temporally related observations.

## OTLP normalization

`opentelemetry-proto` parses `ExportMetricsServiceRequest`,
`ExportLogsServiceRequest`, and `ExportTraceServiceRequest`. One converter handles
all OTLP `AnyValue` variants: string, boolean, integer, double, array, key/value
list, and bytes. Each observation inherits `service.name` from its own resource;
missing names become `__unknown__` and remain visible in quality reporting.

Event timestamps are metric datapoint `time_unix_nano`, log
`time_unix_nano` with `observed_time_unix_nano` fallback, and span
`start_time_unix_nano`. Span duration is end minus start. Missing/invalid event
times are never fabricated; they are dropped from aggregation and fail a build
when their configurable ratio exceeds the default `0.01`. Negative durations
are excluded from duration statistics and counted.

## Windowing and identity

The default is a 60-second UTC tumbling window with `[start, end)` boundaries.
Integer nanosecond floor division makes boundaries deterministic. Grouping always
includes run ID and service, so labeled runs cannot mix. Service and metric window
IDs are SHA-256 hashes of schema version plus their complete logical keys.

Source records are deduplicated before observation expansion. Identical content
with the same event ID contributes once; conflicting content for the same ID
fails. Phase 1 lines without Kafka IDs receive deterministic content identities.

## Feature semantics

Logs use OTLP severity numbers, never words from the body. Traces use explicit
OTLP `ERROR` status and span kinds. Percentiles use deterministic linear
interpolation at `(n - 1) * q` for p50, p95, and p99.

`service_windows.parquet` is a stable wide table of log, span, metric-volume, and
telemetry-volume features. `metric_windows.parquet` is long-form by metric name,
unit, and type. Gauge/Sum values are summarized conservatively without counter
rates. Histogram/ExponentialHistogram uses only provided count, sum, min, and max;
v1 does not invent exact bucket percentiles. Summary count/sum/mean is retained.

Structural absence produces zero counts and safe zero rates. Undefined body,
duration, or type-inapplicable metric statistics stay null. NaN and infinities
are rejected. No data-driven imputation or scaler is fitted before Phase 5.

## Leakage prevention and schema versioning

`feature_catalog_v1.json` explicitly and independently lists metadata, targets,
and predictive feature columns for both tables. `run_id`, `scenario`, `label`,
`is_anomaly`, fault flags, and capture provenance cannot enter the feature API.
Tests enforce this boundary. Every row contains `feature_schema_version = 1`;
meaning-changing behavior requires a new version rather than silently redefining
v1.

## Output and quality gates

```text
data/features/<deterministic-dataset-id>/
|-- service_windows.parquet
|-- metric_windows.parquet
|-- manifest.json
`-- quality.json
```

The manifest records lineage, row counts, services, targets, ordered column roles,
library versions, configuration, duplicates, invalid observations, source hashes,
input size, and duration. Quality reports signal/service counts, windows, classes,
scenarios, missing timestamps, invalid durations, unknown service observations,
non-finite values, duplicates, and drops.

`validate` reopens both Parquet files and independently checks required column
order, schema version, row counts, unique/recomputed IDs, targets, finite numeric
features, valid ranges, and manifest consistency. It does not trust sidecars alone.

## Commands

From the repository root:

```powershell
conda activate aegis
python -m pip install -e "ml\feature_engineering[test]"

python -m aegis_features.cli inspect `
  --run 20261005T095734Z-normal-6cc5c1

python -m aegis_features.cli build `
  --run 20261005T095734Z-normal-6cc5c1 `
  --run 20261005T095842Z-cpu-saturation-cd027d `
  --window-seconds 60

python -m aegis_features.cli validate --dataset phase4-v1-74f868854916
python -m aegis_features.cli summary --dataset phase4-v1-74f868854916

python -m pytest ml\feature_engineering\tests
python -m ruff check ml\feature_engineering
```

The dataset ID depends on source hashes and configuration; it changes when the
inputs or schema-relevant configuration changes.
