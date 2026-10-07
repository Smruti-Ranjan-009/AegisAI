# Phase 5 anomaly detection

## Scope

Phase 5 is an offline, reproducible anomaly experiment over Phase 4 Parquet
features. It adds no prediction API, Kafka inference, automatic incident
creation, classifier, MLflow tracking, RAG, Redis, or cloud deployment. The
production `services/ml-service` remains a health-only shell.

## Capture campaign and readiness

The committed `anomaly-v1` plan requires six normal runs and two independent
runs for each of `cpu_saturation`, `memory_leak`, `service_failure`,
`dependency_failure`, and `high_latency`. Captures are interleaved to reduce
order confounding. New runs use a 20-second warmup, 60-second capture, 7-second
fault propagation delay, 3-second collector flush, and 15-second post-fault
cooldown. Feature flags are restored and verified after each run. The email
service is restarted after memory-leak runs because disabling future retention
does not reclaim memory already retained by the process.

Every run must pass Phase 1 validation. Final training additionally requires at
least 150 eligible normal service-window rows. The two legacy 30-second runs
are intentionally not mixed with the 60-second campaign.

```powershell
conda activate aegis
python scripts\telemetry_lab.py campaign --plan anomaly-v1
$campaign = Get-Content .runtime\telemetry-lab\campaigns\anomaly-v1-result.json -Raw |
    ConvertFrom-Json
$featureArgs = @("-m", "aegis_features.cli", "build", "--window-seconds", "60")
foreach ($run in $campaign.accepted_runs) {
    $featureArgs += @("--run", $run.run_id)
}
python @featureArgs

python -m aegis_anomaly.cli readiness --dataset <dataset-id>
```

## Ground truth and service eligibility

Two labels are kept distinct:

- `run_has_fault`: the capture ran a fault scenario.
- `is_injected_fault_service`: the service is in that scenario's authoritative
  `expected_affected_services` list in `infrastructure/telemetry-lab/scenarios.json`.

Rows from non-target services in fault runs are propagation-ambiguous. They
participate in run-level detection but are not treated as normal negatives in
the primary service-localization evaluation.

The initial application detector excludes `__unknown__`, `flagd`,
`load-generator`, `otelcol-contrib`, and `telemetry-docs`. These identities
represent missing resource attribution or telemetry/test infrastructure. The
remaining observed application identities are eligible. `service_name` stays
metadata and is never a model feature.

## Leakage controls

All rows from one `run_id` belong to exactly one split. With the minimum
campaign, four normal runs train the detector, one normal plus one run from
each fault scenario form validation, and the corresponding remaining runs form
the untouched test set. The assignment is deterministic with seed 42.

Only normal training rows fit metric baselines, imputation, robust scales, and
detectors. Validation chooses the detector and calibrates its threshold. Test
data is scored once after feature rules, selection, and threshold are frozen.
Identifiers, timestamps, service/scenario labels, targets, dataset paths, and
fault configuration cannot enter `X`.

## Feature matrix and metric baselines

The matrix starts with the exact predictive columns in Phase 4's versioned
service-window catalog. A fitted metric transformer adds eight compact features:

```text
metric_baseline_count
metric_missing_baseline_count
metric_coverage_ratio
metric_abs_deviation_mean
metric_abs_deviation_max
metric_abs_deviation_p95
metric_deviation_over_3_count
metric_deviation_over_5_count
```

Metric keys preserve service, metric name, unit, type, and statistic. Gauge
means, histogram/exponential-histogram means, and summary means are eligible.
Raw Sum values are excluded because Phase 4 does not preserve enough
temporality/reset information to distinguish safe counter rates from cumulative
values.

Location is the median. Scale is `1.4826 × MAD`, then `IQR / 1.349` when MAD is
zero. A remaining zero-scale baseline uses finite unit scale and contributes
zero deviation because it is uninformative. Services need five normal training
windows before service-specific baselines are trusted; otherwise the transformer
uses a global metric-semantic fallback. Unseen evaluation metrics increment the
missing-baseline count and never mutate fitted state.

## Detectors, threshold, and selection

The transparent baseline computes absolute robust z-scores per feature and uses
the mean of the five largest deviations as its anomaly score. It also reports
top contributing features. Isolation Forest uses 300 trees, `max_samples=auto`,
`contamination=auto`, `random_state=42`, and one worker for reproducibility.
Both expose larger scores as more anomalous.

Each detector receives a threshold at the 95th percentile of normal validation
scores, targeting a 5% row-level normal false-positive rate without using fault
labels. Selection minimizes validation FPR distance from the target, then
prefers run recall, Hit@1, service ROC-AUC, and finally the simpler robust model.
There is no fabricated minimum F1 quality gate.

## Evaluation and artifacts

Final reports include service-level ROC-AUC, PR-AUC, precision, recall, F1,
normal FPR, and confusion matrix; run-level maximum-score detection; per-scenario
and per-service outcomes; and fault localization Hit@1, Hit@3, and MRR. Undefined
AUCs are recorded as null rather than fabricated.

Generated artifacts live in ignored `artifacts/anomaly_detection/<model-id>/`:

```text
model.joblib
manifest.json
metrics.json
threshold.json
feature_schema.json
split.json
training_report.json
evaluation_predictions.parquet
```

The model ID hashes dataset, split, detector, feature schema, and threshold
configuration. The bundle contains the metric transformer, median imputer,
feature order, detector, and threshold. Training reloads the saved bundle and
requires exactly identical test scores. Joblib is pickle-based and artifacts
must only be loaded from trusted sources.

## Commands

```powershell
conda activate aegis
python -m pip install -e "ml\anomaly_detection[test]"

python -m aegis_anomaly.cli readiness --dataset <dataset-id>
python -m aegis_anomaly.cli train --dataset <dataset-id>
python -m aegis_anomaly.cli evaluate --model <model-id>
python -m aegis_anomaly.cli score --model <model-id> --dataset <dataset-id>

python -m pytest ml\anomaly_detection\tests
python -m ruff check ml\anomaly_detection
```

This remains a portfolio-scale synthetic campaign. Scores may reflect demo
traffic patterns and injected feature-flag mechanics; downstream fault
propagation is not exhaustively labeled, and results must not be generalized to
production incident distributions without new data and evaluation.

## Measured local result

The validated `anomaly-v1` campaign accepted 16 runs: six normal and two for
each fault scenario. One initial normal attempt was rejected before capture
because Checkout was unhealthy during first-time demo startup; no rejected raw
run entered the dataset. Dataset `phase4-v1-d0a2e0c1e709` contains 561 service
windows and 9,806 metric windows, including 222 normal service windows and 159
eligible normal service windows.

The deterministic split was:

```text
training (normal only)
  20261006T163527Z-normal-15383c
  20261006T164048Z-normal-2fd57e
  20261006T164609Z-normal-beb8c2
  20261006T165514Z-normal-b8f8f8

validation
  20261006T163334Z-service-failure-3ef506
  20261006T163854Z-high-latency-14c4b2
  20261006T164415Z-cpu-saturation-0efb0a
  20261006T164932Z-memory-leak-d0e340
  20261006T165129Z-dependency-failure-218ba1
  20261006T165321Z-normal-c3df5a

test
  20261006T162755Z-cpu-saturation-cd2dfc
  20261006T163004Z-normal-7f2a1c
  20261006T163133Z-memory-leak-95dfc9
  20261006T163701Z-dependency-failure-8b6645
  20261006T164217Z-service-failure-6f492a
  20261006T164740Z-high-latency-de52da
```

There is zero run overlap. The model matrix has 46 features and 107 training,
138 validation, and 150 test rows. Training created 87 service-specific and 51
global metric baselines; all eligible services had at least eight normal
training windows. The safe counter policy excluded 7,126 Sum rows from raw
metric-deviation calculations.

Both validation thresholds produced a 3.85% service-level normal FPR against
the 5% target. The robust detector's validation service ROC-AUC/PR-AUC/F1 were
0.510/0.433/0.286, with Hit@1 0.00, Hit@3 0.40, and MRR 0.308. Isolation
Forest's corresponding results were 0.570/0.473/0.400, with Hit@1 0.40, Hit@3
0.60, and MRR 0.562. Both detected all five validation fault runs and falsely
detected the single validation normal run. The frozen rule therefore selected
Isolation Forest. Its normal-validation score range was 0.3341–0.5973, median
0.3901, p95 0.5341, and threshold 0.5359423345.

On the untouched test set, primary service-level ROC-AUC was 0.651, PR-AUC
0.444, precision 0.455, recall 0.417, F1 0.435, and normal FPR 0.231. The
confusion matrix was TN=20, FP=6, FN=7, TP=5; 112 propagated fault-run rows were
excluded as ambiguous. Run-level ROC-AUC was 0.20, PR-AUC 0.81, precision 0.833,
recall 1.0, and F1 0.909: all five fault runs were detected, but the only normal
test run was also falsely detected. Localization was Hit@1 0.20, Hit@3 0.60,
and MRR 0.46.

Target-window recall by test scenario was CPU saturation 0.50, dependency
failure 0.667, high latency 0.25, memory leak 0.00, and service failure 0.50.
Memory leak was not detected through its injected email-service row, and CPU,
memory, dependency, and latency localization frequently ranked unrelated noisy
services above the injected target. These weak and unstable results are a
material Phase 5 limitation, not a production quality claim. The test set has
only one run per class, 60-second captures create partial UTC boundary windows,
and the OpenTelemetry Demo workload is synthetic.

Artifact `anomaly-v1-4c84405c580f` is 373,272 bytes and reload verification is
exact. Local detector training/evaluation took 1.504 seconds; selected-detector
test scoring took 0.0168 seconds for 150 rows (about 8,908 rows/sec or 0.112 ms
per row). The full CLI scoring path, including dataset loading and feature
transformation, processed 395 eligible rows in 0.203 seconds (about 1,942
rows/sec or 0.515 ms per row).
