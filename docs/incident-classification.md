# Phase 6 incident classification

## Objective and two-stage architecture

Phase 6 is an offline five-class classifier answering which known incident type
an already abnormal run resembles. It follows, rather than replaces, the Phase
5 detector:

```text
labeled OTLP telemetry
  -> Phase 4 feature engineering
  -> frozen Phase 5 anomaly scoring
  -> top-three abnormal telemetry context
  -> one service-independent row per run
  -> Phase 6 incident probabilities
```

Supported targets are `cpu_saturation`, `memory_leak`, `service_failure`,
`dependency_failure`, and `high_latency`. `normal` is intentionally not a class;
the upstream anomaly gate decides whether classification is appropriate.

## Frozen anomaly dependency and threshold semantics

Phase 6 requires trusted local model `anomaly-v1-4c84405c580f`. Its metric
baseline transformer, median imputer, 46-feature order, Isolation Forest, and
threshold `0.5359423344799236` are loaded without fitting or mutation.

The threshold is slightly higher than the reported interpolated normal-score
p95 `0.5341476669796773`. Calibration used
`numpy.quantile(..., method="higher")`, selecting an observed order statistic,
while the distribution summary used NumPy's default linear interpolation.
Decisions use strict `score > threshold`. This is expected behavior, not a Phase
5 defect.

Joblib is pickle-based and may execute code while loading. Only locally
generated, trusted artifacts are supported.

## Capture campaign and readiness

`classification-v1` reuses two validated Phase 5 fault runs per class and
captures four additional runs per class. The deterministic order interleaves
all five scenarios. New captures use a 20-second warmup, 60-second capture,
7-second fault propagation, 3-second collector flush, and 15-second cooldown.
Flags are restored and verified after each fault, affected services are checked,
and email is restarted after memory-leak runs.

Every accepted run must pass the existing Phase 1 validator. Classification
readiness requires at least six compatible validated runs for each of the five
classes, exactly one dataset row per run, finite catalog-owned features, a valid
frozen artifact, and no development/test overlap.

## Run representation and leakage controls

The frozen anomaly bundle scores every eligible service/window. Rows are sorted
by descending anomaly score; window start, service name, and window ID are used
only as deterministic metadata tie-breakers. The three highest-scoring rows are
aggregated into one run vector.

The versioned v1 catalog contains 30 features in these groups:

- six anomaly-score and context-size summaries;
- eight frozen metric-baseline deviation/coverage summaries;
- six log volume/rate summaries;
- seven trace volume/error/latency summaries;
- three metric/combined telemetry volume summaries.

`scenario`, `run_id`, `service_name`, expected fault services, fault flags,
injected-service labels, capture paths, filenames, and window IDs cannot enter
the predictive catalog or classifier matrix. Service identity is not encoded,
pivoted, hashed, embedded, or included in a feature name. Telemetry behavior can
still indirectly expose service identity, which is an explicit dataset
limitation.

Generated datasets live under ignored `data/classification/<dataset-id>/` with
`incident_runs.parquet`, `manifest.json`, `quality.json`, and `split.json`.

## Frozen split and cross-validation

Dataset construction freezes two newly captured runs per class as the final
test using deterministic seed-42 hashes. The remaining four runs per class form
the 20-row development set. Test IDs are persisted before model comparison.

Development comparison uses `StratifiedKFold(n_splits=4, shuffle=True,
random_state=42)`. Each fold fits its own complete sklearn pipeline:

- Logistic Regression: median imputer, `StandardScaler`, `LogisticRegression`;
- Random Forest: median imputer, `RandomForestClassifier` without scaling.

Selection uses highest mean CV macro F1. A difference no larger than 0.01 is a
practical tie, followed by balanced accuracy, lower macro-F1 variation, and
Logistic Regression simplicity. The final test is not used in selection.

After selection, the winning pipeline is refitted on all development runs and
then evaluated once on the frozen test. Probabilities are not calibrated and
must not be interpreted as calibrated confidence. Phase 6 does not fabricate an
`unknown` class; a future anomaly-plus-low-confidence path may route unfamiliar
incidents to human investigation.

## Artifacts and explainability

Generated models live under ignored
`artifacts/incident_classification/<model-id>/`:

```text
model.joblib
manifest.json
metrics.json
split.json
feature_schema.json
cv_results.json
test_predictions.parquet
report.json
```

The bundle persists the complete preprocessing/classifier pipeline, feature and
class ordering, aggregation contract, and Phase 5 lineage. Reload validation
requires exact prediction and probability equality. Logistic models report
standardized class coefficients; Random Forest models report impurity-based
feature-importance diagnostics. Neither is causal evidence.

## Measured local result

The completed campaign accepted 30 compatible 60-second fault runs: six per
class, comprising ten existing Phase 5 runs and twenty new Phase 6 runs. Two
attempts were rejected by predefined validity gates: one CPU attempt when
Checkout was unhealthy before capture, and one memory attempt whose telemetry
did not contain the expected email service. A high-latency raw directory from an
execution-environment interruption was never checkpointed as accepted and was
also excluded. The resumable campaign later completed with status PASS.

Phase 4 dataset `phase4-v1-45ebffa2ddf3` contains 1,091 service windows and
18,116 metric windows. Its internal build duration was 33.521 seconds and its
quality result was PASS. The immutable Phase 5 artifact scored 776 eligible
service/windows, emitted 219 strict threshold decisions, and produced finite
scores from `0.332997` to `0.713745` with no fitting or failures.

Classification dataset `classification-v1-1090d5095a33` contains 30 rows and 30
predictive features, with six rows per class. Generation took 0.556 seconds.
The persisted split contains 20 development and 10 newly captured final-test
runs with no overlap.

Four-fold development results:

| Model | Macro F1 mean | Macro F1 std | Balanced accuracy | Accuracy | Top-2 accuracy |
|---|---:|---:|---:|---:|---:|
| Logistic Regression | 0.100 | 0.122 | 0.150 | 0.150 | 0.400 |
| Random Forest | 0.303 | 0.132 | 0.350 | 0.350 | 0.400 |

Random Forest won by the predeclared macro-F1 rule. Final untouched test:

```text
accuracy             0.300
balanced accuracy    0.300
macro precision      0.307
macro recall         0.300
macro F1             0.270
weighted F1          0.270
top-2 accuracy       0.600
ROC-AUC OVR macro    0.625
log loss             1.510
```

Confusion matrix, rows actual and columns predicted, in class order CPU,
memory, service, dependency, high latency:

```text
             CPU  memory  service  dependency  latency
CPU            0       1        1           0        0
memory         0       1        1           0        0
service        0       1        1           0        0
dependency     1       0        0           1        0
latency        0       2        0           0        0
```

CPU and high-latency recall were zero. Memory, service, and dependency each
classified one of two runs correctly. Several predictions had small gaps
between first and second probabilities, including one service-failure run at
`0.377` versus `0.372`; probabilities are uncalibrated. No post-test retuning
was performed.

The largest Random Forest impurity diagnostics were
`anomaly_score_std_top3` (0.094), `span_duration_ms_p99_top3_max` (0.059),
`span_error_rate_top3_max` (0.055), `anomaly_score_max` (0.053), and
`span_duration_ms_mean_top3_mean` (0.053). These describe associations in this
small fitted model, not causes.

Final model `classifier-v1-d37b9861572f` is a 66,012-byte trusted joblib bundle.
CV took 2.086 seconds, the final fit 0.408 seconds, and final-test scoring 0.0182
seconds (approximately 551 runs/second). Reload reproduced predictions and
probabilities exactly.

## Reproduction commands

```powershell
conda activate aegis
python -m pip install -e "ml\feature_engineering[test]"
python -m pip install -e "ml\anomaly_detection[test]"
python -m pip install -e "ml\incident_classification[test]"

python scripts\telemetry_lab.py campaign --plan classification-v1

$campaign = Get-Content .runtime\telemetry-lab\campaigns\classification-v1-result.json -Raw |
    ConvertFrom-Json
$featureArgs = @("-m", "aegis_features.cli", "build", "--window-seconds", "60")
foreach ($run in $campaign.accepted_runs) {
    $featureArgs += @("--run", $run.run_id)
}
python @featureArgs

python -m aegis_classifier.cli anomaly-score --feature-dataset <phase4-dataset-id>
python -m aegis_classifier.cli build --feature-dataset <phase4-dataset-id>
python -m aegis_classifier.cli readiness --dataset <classification-dataset-id>
python -m aegis_classifier.cli train --dataset <classification-dataset-id>
python -m aegis_classifier.cli evaluate --model <classifier-model-id>
python -m aegis_classifier.cli score --model <classifier-model-id> --dataset <classification-dataset-id>
```

## Limitations

- Controlled synthetic faults and OpenTelemetry Demo workload only.
- Six independent runs per class and ten final test cases are small samples.
- Only five known incident categories are represented.
- Fault scenarios remain correlated with particular services even though direct
  identity features are excluded.
- Shared infrastructure and secondary propagation can shape telemetry.
- No unknown-incident examples, probability calibration, production traffic,
  model serving, drift monitoring, or online evaluation are included.
