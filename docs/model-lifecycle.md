# Phase 7 model lifecycle

## Objective and boundary

Phase 7 adds local MLflow 3.17.0 experiment tracking, dataset/model lineage,
integrity checks, registry versions, aliases, promotion, rollback, and auditing
around the already frozen Phase 5 and Phase 6 models. It does not retrain,
retune, serve, or automatically invoke either model.

The tracked path is:

```text
phase4-v1-d0a2e0c1e709
  -> anomaly-v1-4c84405c580f
  -> phase4-v1-45ebffa2ddf3
  -> classification-v1-1090d5095a33
  -> classifier-v1-d37b9861572f
  -> MLflow registry aliases
```

The MLflow runs are truthful retrospective imports and carry
`lifecycle.import_mode=frozen_artifact_import`. They do not pretend MLflow was
running during Phase 5/6 training.

## Local architecture

The default metadata store is `.runtime/mlflow/mlflow.db` using SQLite. Logged
artifacts live below `.runtime/mlflow/artifacts`. This is intentionally separate
from incident-service PostgreSQL, uses no permanent container, and supports
direct CLI operation without an always-on server. Environment overrides are
`MLFLOW_TRACKING_URI`, `MLFLOW_ARTIFACT_ROOT`, and the developer/test-oriented
`AEGIS_MLFLOW_RUNTIME_ROOT`.

Stable resources:

| Purpose | Name |
|---|---|
| Anomaly experiment | `aegisai-anomaly-detection` |
| Classification experiment | `aegisai-incident-classification` |
| Anomaly registry model | `AegisAI-AnomalyDetector` |
| Classifier registry model | `AegisAI-IncidentClassifier` |

## Frozen artifacts and integrity

The canonical project outputs remain outside MLflow:

| Model | Canonical joblib SHA-256 | Manifest SHA-256 |
|---|---|---|
| `anomaly-v1-4c84405c580f` | `35a5cb5adb4e7c8fe35f069aefbef68ae61a53c6df79fc9e38c1446379e49704` | `318dcd38112f5bee169a99ff4b6246ab1b30c164855e37b38687dec81c5b9778` |
| `classifier-v1-d37b9861572f` | `a9b24d3a13464af927ce47c3258a28432e4c0d36cce6a377013dfecc565107b7` | `dd975a7f87d377b725a3a36be81a29341ec02a0717c339a325d7fc97e8ae1e48` |

Imports validate normal trusted project loaders, model IDs, feature schema v1,
feature ordering, and classifier-to-anomaly lineage. Compact manifests,
quality reports, splits, schemas, catalogs, reports, a model card, and a hash
manifest are logged. Raw OTLP, JSONL, and generated Parquet are deliberately
excluded.

An identical model ID/hash import reuses its existing version. Reusing a model
ID with a different canonical hash fails with
`artifact_integrity_mismatch`; missing classifier upstream lineage fails with
`upstream_dependency_missing`.

## Model representations and signatures

The anomaly model is an MLflow PyFunc around the complete trusted Phase 5
bundle. Its signature accepts the 46 ordered numeric model features and returns
`anomaly_score` plus the strict `is_anomaly` decision. Its persisted baseline
transformer, imputer, Isolation Forest, feature ordering, and threshold remain
in the canonical bundle; no fitting occurs.

The classifier is the frozen sklearn median-imputer/Random-Forest pipeline. Its
signature accepts 30 ordered numeric run features and returns the predicted
class. Class ordering is logged as model metadata and the original classifier
bundle remains an auxiliary artifact. MLflow's explicit cloudpickle format is
used because its default skops validation rejects trusted Random Forest tree
internals. Both pickle-family representations are trusted-only.

Input examples contain predictive numeric columns only. They exclude run IDs,
scenarios, services, fault flags, expected services, and capture paths.

## Experiments, metrics, and limitations

Local experiment IDs are `1` for anomaly detection and `2` for classification.
The successful imports are:

| Model | Run ID | Registry version |
|---|---|---:|
| Anomaly | `dfe364018fa24c6ca3691141faed91c9` | 1 |
| Classifier | `5e13ba2c69bf4ab98c22327db5a4931e` | 1 |

The anomaly run preserves Phase 5 detector configuration, threshold policy,
split counts, validation/test service metrics, test run metrics, and
localization metrics. The classifier run preserves both candidate CV summaries,
Random Forest parameters, final test metrics, and per-class metrics. Rejected
candidate comparison metrics are logged as historical comparison values, not
as fabricated registered model artifacts.

Known Phase 5 limitations remain visible: test service F1 `0.4348`, a false
positive on the normal test run, weak memory-leak localization, and a small
controlled dataset. Known Phase 6 limitations remain visible: accuracy `0.30`,
macro F1 `0.2705`, zero CPU/high-latency test recall, two test runs per class,
and uncalibrated probabilities. Registration does not imply production quality.

## Candidate, champion, promotion, and rollback

`candidate` identifies the most recently imported validated version;
`champion` is the authoritative future-consumer route. Both currently resolve
to version 1 for both registered models:

```text
models:/AegisAI-AnomalyDetector@champion
models:/AegisAI-IncidentClassifier@champion
```

Promotion validates version existence, approved status, supported schema,
finite required metrics, source hash/model ID, lineage artifacts, signature,
trusted reload, smoke inference, and classifier upstream anomaly resolution.
It deliberately imposes no new performance threshold after test observation.

Rollback runs the same gates and reassigns `champion` without deleting model
versions. When a champion is displaced it is retained through
`previous_champion`. Real rollback is not yet actionable because each real
registry model has only one version; two-version behavior is verified using a
temporary SQLite registry test.

Alias changes append compact records to ignored
`.runtime/mlflow/audit.jsonl`, including prior/new champion, timestamp,
validation result, and human reason.

## Optional UI and security

```powershell
mlflow server `
  --host 127.0.0.1 `
  --port 5000 `
  --backend-store-uri sqlite:///./.runtime/mlflow/mlflow.db `
  --artifacts-destination ./.runtime/mlflow/artifacts
```

Open `http://127.0.0.1:5000` and stop with `Ctrl+C`. Phase 7 supplies no
authentication, so the server must not be exposed publicly. Logging helpers
reject keys containing `password`, `secret`, `token`, `api_key`, or
`access_key`. Credentials and environment dumps must never be logged.

## Measured local lifecycle result

- Frozen anomaly import: `3.580 seconds`.
- Frozen classifier import: `3.287 seconds`.
- Champion lookup: `0.037–0.038 seconds`.
- Champion verification including load/smoke inference: approximately `2.380 seconds` each.
- SQLite database: `1,036,288 bytes`.
- MLflow artifact store: `1,698,581 bytes`, including the recorded failed pre-registration classifier logging attempt.
- Logged anomaly model directory: `531,178 bytes`.
- Logged classifier model directory: `422,529 bytes`.

These are local lifecycle-operation measurements, not inference API latency.

## Reproduction commands

```powershell
conda activate aegis
python -m pip install -e "ml\anomaly_detection"
python -m pip install -e "ml\incident_classification"
python -m pip install -e "ml\model_lifecycle[test]"

python -m aegis_lifecycle.cli --json init
$anomalyImport = python -m aegis_lifecycle.cli --json import-anomaly --model-id anomaly-v1-4c84405c580f | ConvertFrom-Json
$anomalyVersion = $anomalyImport.version
python -m aegis_lifecycle.cli --json promote --model anomaly --version $anomalyVersion --reason "Phase 7 initial validated baseline"
$classifierImport = python -m aegis_lifecycle.cli --json import-classifier --model-id classifier-v1-d37b9861572f | ConvertFrom-Json
$classifierVersion = $classifierImport.version
python -m aegis_lifecycle.cli --json promote --model classifier --version $classifierVersion --reason "Phase 7 initial validated baseline"
python -m aegis_lifecycle.cli --json verify --model anomaly --alias champion
python -m aegis_lifecycle.cli --json verify --model classifier --alias champion
python -m aegis_lifecycle.cli --json audit
```

The import output supplies the actual MLflow-assigned version; automation does
not assume a clean registry or hardcode version `1`.
