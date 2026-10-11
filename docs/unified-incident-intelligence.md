# Unified incident intelligence

Phase 12 connects the already frozen incident, anomaly, classification, retrieval,
reranking, and grounded-generation components. It is application integration, not
a new quality benchmark. The formal generation-quality baseline remains
[Phase 11 RAG evaluation](rag-evaluation.md).

## Ownership and runtime architecture

```text
validated Phase-4-compatible feature windows
                    |
                    v
incident-service (domain/orchestration authority)
   |                |
   | HTTP           | HTTP, only after anomaly
   v                v
ml-service       rag-service
   |                |
   + anomaly        + Phase 9 BM25 + dense + RRF
   + classifier     + Phase 10 MiniLM reranker
                    + top-five evidence
                    + local Qwen3-4B Q4_K_M
                    + schema/citation validation
                    |
                    v
incident-service Flyway persistence + timeline
                    |
                    v
mandatory human review (no action execution)
```

The Java service owns incident existence, the intelligence-run resource,
idempotency, state transitions, the timeline, and persistence. Python owns model
and RAG computation. Python Alembic still owns only the `rag` schema. Kafka does
not trigger diagnosis in this phase.

The HTTP sequence is synchronous. Database transactions are short: a unique
atomic claim is committed before an external request; each later state update is
committed separately. ML uses 2-second connect and 15-second read timeouts. RAG
uses 2-second connect and 330-second read timeouts. There is no automatic retry
around generation.

## ML service contract

- `GET /health`: process liveness only.
- `GET /ready`: succeeds only after the configured providers load.
- `GET /api/v1/models`: safe model identities, feature schema, and load state.
- `POST /api/v1/inference/analyze`: `ml_inference_v1` input and
  `ml_inference_result_v1` output.

The request is a model-ready feature boundary, not raw telemetry. Each request
has an `input_id`, feature schema version 1, the exact ordered 46-feature frozen
Phase 5 schema, and one or more windows with service, ID, UTC bounds, and values.
Numeric values must be finite. Nulls are allowed only to preserve the frozen
median-imputation behavior. Raw telemetry must first pass through the existing
Phase 4 engineering pipeline; Phase 12 does not rewrite it.

The service scores every window with `anomaly-v1-4c84405c580f`. A score is an
`anomaly_score`, never confidence, and the frozen decision remains strictly
`score > 0.5359423344799236`. If no window exceeds the threshold, classification
is skipped. Otherwise the unchanged Phase 6 top-three aggregation adapter builds
the exact 30-feature classifier input and
`classifier-v1-d37b9861572f` returns the predicted class plus all five class
probabilities: `cpu_saturation`, `memory_leak`, `service_failure`,
`dependency_failure`, and `high_latency`.

`AEGIS_ML_MODEL_SOURCE` selects `fake`, `artifact`, or `mlflow`. `artifact`
verifies and loads trusted local frozen joblib bundles. `mlflow` first resolves
the Phase 7 champion aliases and retains their immutable model URIs while using
the same trusted artifacts for the online aggregation boundary. Missing or
inconsistent configured models make readiness fail; there is no fallback.

## RAG service contract

- `GET /health`: process liveness only.
- `GET /ready`: fake-mode deterministic readiness, or real PostgreSQL corpus,
  reranker, verified GGUF, and llama.cpp health.
- `POST /api/v1/diagnose`: `rag_diagnosis_v1` structured context and
  `rag_diagnosis_result_v1` output.

`incident_query_v1` deterministically includes the incident title, description,
affected services, observed signal summary, anomaly score/threshold, and the
classifier result. It labels classification as an **unverified machine hint, not
ground truth**. It contains no qrels, expected answers, gold facts, or evaluation
labels. Canonical retrieval applies no predicted-class metadata filter, because
a classifier error must not eliminate relevant evidence.

Real mode composes the existing Phase 9 `HybridRetriever`, Phase 10
`RerankingPipeline`, `GroundedGenerator`, and `LocalLlamaCppProvider`. The frozen
BGE identity, BM25 k1 1.5/b 0.75, RRF k 60, candidate depth 10, evidence depth 5,
MiniLM revision, Qwen identity/quantization, deterministic decoding, and
`grounded_incident_v1` prompt are unchanged. Source paths and headings in
citations are reconstructed server-side from evidence IDs. The response exposes
compact evidence references, lineage, and timings, not full prompt bodies or
chunks.

The offline Phase 11 DeBERTa NLI evaluator is deliberately absent from the
runtime path: it measures the system and is not a calibrated production safety
gate.

## Incident API and states

- `POST /api/v1/incidents/{incidentId}/intelligence-runs`
- `GET /api/v1/incidents/{incidentId}/intelligence-runs`
- `GET /api/v1/incidents/{incidentId}/intelligence-runs/{runId}`

The POST validates the incident and `intelligence_v1` request, hashes canonical
semantic JSON, atomically claims a row, calls ML, stops on an anomaly-negative
result, otherwise calls RAG, validates its governance/citation contract, persists
the result, and appends an existing incident timeline entry.

| State | Meaning |
| --- | --- |
| `PENDING` | Atomic run claim exists. |
| `RUNNING` | Orchestration started. |
| `NO_ANOMALY_SIGNAL` | Frozen score did not exceed threshold; classifier/RAG skipped. |
| `GROUNDED_ADVISORY` | Structured claims/actions and citations validated. |
| `INSUFFICIENT_EVIDENCE` | RAG abstained; this is not a dependency failure. |
| `FAILED_ML` | ML was unavailable or rejected inference; RAG was not called. |
| `FAILED_RAG` | ML was retained but RAG/generation was unavailable. |
| `FAILED_VALIDATION` | An upstream response, including citations, violated contract. |

The no-anomaly state is a model output and is not proof that the system is
healthy. Grounded and insufficient-evidence outcomes both require human review.

## Persistence, idempotency, correlation, and lineage

Flyway V7 creates `incident_intelligence_runs`. UUID identity, incident foreign
key, 64-character SHA-256 request hash, state, schema/input identity, correlation
ID, governance flag, failure fields, timestamps, and optimistic version are
relational. Bounded versioned ML result, intelligence result, lineage, and timing
snapshots use JSONB. The unique `(incident_id, request_hash)` constraint is the
concurrency authority; an exact retry returns the existing row without a second
model/generation call. Changed semantic input creates another run. Correlation
headers, random IDs, and attempt timestamps are not hashed.

`X-Correlation-ID` is accepted or generated by incident-service, sent unchanged
to ML and then RAG, returned in headers and bodies, and recorded on the run. It
does not affect business behavior.

Persisted lineage identifies the feature schema/order, anomaly and classifier
model IDs/source/hashes or MLflow URIs, corpus fingerprint, embedding contract,
BM25/RRF settings, reranker identity/revision, evidence IDs/chunks, prompt
version, local Qwen/GGUF identity, deterministic generation settings, and
component timings. Model binaries, full prompts, database URLs, credentials, and
full evidence bodies are not stored.

## Governance and security

All SLM-generated diagnoses are advisory and always carry
`requires_human_review=true`. Suspected causes and recommended actions are data
only. No code executes shell commands, restarts services, edits infrastructure,
invokes tools, or performs remediation. Service origins come only from trusted
configuration. Qwen is local-only; no hosted LLM or arbitrary URL fetching is
present. Logs include IDs, state, and latency, not feature arrays, prompts,
secrets, model weights, or corpus bodies.

Phase 11 found substantial unsupported-claim and adversarial weaknesses (including
22/56 supported claims and 0/3 strict adversarial cases). Runtime wiring does not
erase those limitations. Human review is mandatory.

## Local startup

Fake mode is the reproducible integration workflow:

```powershell
docker compose up -d --build --wait postgres ml-service rag-service incident-service
Invoke-RestMethod http://localhost:8002/ready
Invoke-RestMethod http://localhost:8003/ready
Invoke-RestMethod http://localhost:8080/actuator/health
```

Real native mode requires the Python 3.12 environment with Phase 5–10 and Phase 7
packages installed, the existing populated `aegisai` RAG database, frozen
artifacts, cached pinned BGE/MiniLM files, and the actual loopback llama.cpp
server. Start in dependency order: PostgreSQL, optional MLflow source, ml-service,
llama.cpp, rag-service, incident-service. Set `AEGIS_ML_MODEL_SOURCE=artifact`
or `mlflow` and `AEGIS_RAG_PROVIDER=real`; do not place the GGUF in an image.

## Validation and limitations

The fake-provider suites exercise grounded, anomaly-negative, abstention, ML/RAG
failure, malformed citations, persistence, readback, timeline, idempotency, and
correlation paths over HTTP.

The final real run used fresh input identities ending in
`validation-final-20261011` and the unchanged captured Phase 4-compatible
windows. These are runtime smoke cases, not a new accuracy test set:

| Fault family | Anomaly score/result | Frozen classifier | RAG/run status | Citations | Persisted total |
| --- | --- | --- | --- | ---: | ---: |
| CPU saturation | 0.622842 / anomaly | `cpu_saturation` | grounded / `GROUNDED_ADVISORY` | 5 | 21,390.412 ms |
| Memory leak | 0.677300 / anomaly | `memory_leak` | grounded / `GROUNDED_ADVISORY` | 1 | 9,038.380 ms |
| Service failure | 0.622671 / anomaly | `service_failure` | grounded / `GROUNDED_ADVISORY` | 5 | 22,054.439 ms |
| Dependency failure | 0.647471 / anomaly | `dependency_failure` | citation rejection / `FAILED_VALIDATION` | 0 | 13,854.217 ms |
| High latency | 0.561262 / anomaly | `high_latency` | grounded / `GROUNDED_ADVISORY` | 5 | 28,762.026 ms |

The dependency case is an intentional truthful outcome: the frozen Qwen result
failed exact citation-coverage validation. The API returned no false success,
did not retry generation, and persisted the validation failure.

On this one-machine sample, ML service p50/mean was 40.981/41.086 ms over five
runs. For the four grounded runs, retrieval was 44.621/72.090 ms, reranking
216.801/225.648 ms, and generation 21,264.783/19,916.063 ms. Total persisted
orchestration p50/mean over all five runs was 21,390.412/19,019.895 ms. The
successful-run residual after measured ML and RAG service time—Java
orchestration plus database work, not a pure database benchmark—was
14.045/35.042 ms. Generation dominates local latency.

Known limitations include a small curated corpus, mostly synthetic telemetry,
weak frozen ML metrics for some classes, Phase 11 generation weaknesses, local
llama.cpp operational complexity and latency, mandatory human review, no
autonomous remediation, and no production traffic or SLO evidence.

## Reproduction commands

Run all commands from the repository root unless a block changes directory.
Use the existing Python 3.12 `aegis` environment and JDK 17. Test fixtures must
point only at the isolated `aegis_rag_test` database.

Install the composed runtime dependencies:

```powershell
conda activate aegis
python -m pip install -e ".\ml\feature_engineering[test]"
python -m pip install -e ".\ml\anomaly_detection[test]"
python -m pip install -e ".\ml\incident_classification[test]"
python -m pip install -e ".\ml\model_lifecycle[test]"
python -m pip install -e ".\rag\ingestion[test,embeddings]"
python -m pip install -e ".\rag\retrieval[test]"
python -m pip install -e ".\rag\reranking[test,models]"
python -m pip install -e ".\rag\generation[test]"
python -m pip install -r .\services\ml-service\requirements.txt
python -m pip install -r .\services\rag-service\requirements.txt
```

Start PostgreSQL and configure the frozen artifact provider:

```powershell
docker compose up -d --wait postgres
$env:AEGIS_ML_MODEL_SOURCE = "artifact"
$env:AEGIS_ANOMALY_ARTIFACT_URI = (Resolve-Path ".\artifacts\anomaly_detection\anomaly-v1-4c84405c580f\model.joblib")
$env:AEGIS_CLASSIFIER_ARTIFACT_URI = (Resolve-Path ".\artifacts\incident_classification\classifier-v1-d37b9861572f\model.joblib")
```

For Phase 7 champion resolution, initialize/verify the existing local store and
then select `mlflow` instead. This still uses the same trusted frozen artifacts:

```powershell
python -m aegis_lifecycle.cli --json init
python -m aegis_lifecycle.cli --json verify --model anomaly --alias champion
python -m aegis_lifecycle.cli --json verify --model classifier --alias champion
$env:AEGIS_ML_MODEL_SOURCE = "mlflow"
```

Start ML service in a new terminal after setting the same environment values:

```powershell
conda activate aegis
Set-Location .\services\ml-service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Verify the pinned GGUF and start the loopback-only server in another terminal:

```powershell
conda activate aegis
python -m aegis_rag_generation verify-model --json
llama-server.exe `
  --model .runtime\rag\models\Qwen3-4B-Q4_K_M.gguf `
  --alias aegis-qwen3-4b-q4km `
  --host 127.0.0.1 --port 8081 `
  --ctx-size 4096 --parallel 1 --threads 6 `
  --n-gpu-layers 20 --jinja `
  --chat-template-kwargs '{"enable_thinking":false}'
```

Start RAG and incident services in separate terminals:

```powershell
conda activate aegis
$env:AEGIS_RAG_PROVIDER = "real"
Set-Location .\services\rag-service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

```powershell
$env:ML_SERVICE_URL = "http://127.0.0.1:8002"
$env:RAG_SERVICE_URL = "http://127.0.0.1:8003"
Set-Location .\services\incident-service
.\mvnw.cmd spring-boot:run
```

Exercise the unchanged five-family inputs with a new identity and inspect one
persisted run:

```powershell
$env:AEGIS_PHASE12_VALIDATION_IDENTITY = "manual-$(Get-Date -Format yyyyMMddHHmmss)"
python .\scripts\phase12_real_validation.py
$results = Get-Content -Raw .runtime\phase12-real-validation.json | ConvertFrom-Json
$first = $results.scenarios[0]
Invoke-RestMethod "http://127.0.0.1:8080/api/v1/incidents/$($first.incident_id)/intelligence-runs/$($first.intelligence_run_id)"
```

The POST body captured in `.runtime/phase12-real-ml-request.json` can also be
submitted directly to ML service for serializer-contract inspection. For exact
idempotency replay, resubmit an identical `intelligence_v1` body to the same
incident URL; change a semantic input or `input_id` to create a new run. The
fake-backed integration suite contains deterministic no-anomaly and
insufficient-evidence examples:

```powershell
Set-Location .\services\incident-service
.\mvnw.cmd -Dtest=IntelligenceApiIntegrationTest test
Set-Location ..\ml-service
python -m pytest -q
Set-Location ..\rag-service
python -m pytest -q
```

Run the documented Phase 4–11 regression commands from the root README, then
validate delivery and clean up without deleting named volumes:

```powershell
docker compose config -q
docker compose build
docker compose up -d --wait --wait-timeout 180
docker compose ps
docker compose down --remove-orphans
```
