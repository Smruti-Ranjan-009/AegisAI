# Planned Architecture

Phase 11 preserves the operational service, incident, Kafka, ML, lifecycle, and
knowledge paths and the frozen Phase 10 offline diagnosis pipeline. It adds an
independent offline evaluation loop over write-once final artifacts. The RAG
HTTP service remains health-only; production model serving, frontend,
observability, and cloud capabilities remain future goals.

## Phase 3 Incident Management Path

```text
Operator / API client
        |
        | JSON over HTTP
        v
Spring Boot Incident API
        |
        +--> request validation and Problem Details
        +--> incident lifecycle invariants
        +--> transactional incident + timeline writes
        |
        v
PostgreSQL 18.6 + pgvector 0.8.6
  +-- incidents
  +-- incident_affected_services
  +-- incident_timeline_entries
  +-- flyway_schema_history
```

Flyway is the sole schema owner and Hibernate runs with `ddl-auto=validate`.
Incident and associated timeline writes share transaction boundaries. The API
uses optimistic locking for concurrent aggregate mutations. Kafka is not connected
to this path in Phase 3.

## Phase 1 Offline Dataset Path

```text
OpenTelemetry Demo 3.1.0
        |
        | OTLP logs / metrics / traces
        v
OpenTelemetry Collector
        |
        +--> metrics.jsonl
        +--> logs.jsonl
        +--> traces.jsonl
        +--> manifest.json (ground truth)
                    |
                    v
             Raw Labeled Dataset
```

This isolated path uses the demo's built-in traffic generator and deterministic feature flags. It exists only to generate validated local experiment files. The file exporter is not the intended production architecture, and the telemetry service is not in this capture path. Phase 2 keeps this mode intact and adds the separate AegisAI Kafka event pipeline.

## Phase 4 Offline Feature Path

```text
Phase 1 labeled captures
        |
        v
manifest + metrics/logs/traces JSONL
        |
        v
Official-protobuf OTLP normalization
        |
        v
Event-time run/service windows
        |
        +--> service_windows.parquet
        |
        +--> metric_windows.parquet
        |
        +--> manifest.json + quality.json
```

This installable package is a batch development tool, not another long-running
service. It preserves run/scenario lineage, prevents target leakage through a
versioned column catalog, and validates output by reopening Parquet. It does not
train or serve anomaly models.

## Phase 5 Offline Anomaly Path

```text
Interleaved validated capture campaign
        |
        v
Phase 4 service + metric Parquet
        |
        v
Readiness gate and run-level split
        |
        +--> normal training runs only
        |       |
        |       +--> metric median/MAD baselines
        |       +--> median imputation
        |       +--> robust z-score + Isolation Forest
        |
        +--> validation: selection + normal-only threshold
        |
        +--> untouched test: service/run/localization evaluation
        |
        v
Ignored, reload-verified local artifact bundle
```

The path is a batch development workflow, not another deployed service. Run
boundaries prevent neighboring windows leaking across splits. Scenario
configuration supplies injected-service ground truth, while non-target services
in fault runs remain propagation-ambiguous. No output is published to Kafka or
used to create incidents.

## Phase 6 Offline Classification Path

```text
Labeled OTLP telemetry
        |
        v
Phase 4 Feature Engineering
        |
        v
Frozen Phase 5 Anomaly Detection
        |
        v
anomaly scores / top-three abnormal context
        |
        v
one service-independent row per fault run
        |
        v
development-only stratified cross-validation
        |
        v
offline five-class incident probabilities
```

Phase 6 keeps `normal` outside the classifier and treats
`anomaly-v1-4c84405c580f` as an immutable upstream dependency. Direct service
identity, injected-service metadata, capture provenance, and targets cannot
enter the 30-feature run matrix. Dataset construction freezes two newly
captured runs per class before Logistic Regression and Random Forest are
compared on the remaining development runs. No result is served or connected
to Kafka or the incident API.

## Phase 7 Local Model Lifecycle Path

```text
Telemetry
    |
    v
Feature Engineering
    |
    v
Frozen Anomaly Detection
    |
    v
Frozen Incident Classification
    |
    v
MLflow experiment tracking
    |
    v
SQLite-backed Model Registry
    |
    +--> candidate
    |
    +--> champion
```

Phase 7 retrospectively imports the exact Phase 5 and Phase 6 artifacts. It
logs their original parameters, metrics, limitations, compact dataset lineage,
signatures, model cards, and SHA-256 integrity metadata without retraining.
Registry aliases are promoted only after deterministic integrity, schema,
lineage, reload, and smoke-inference gates. The local store is single-user and
Git-ignored; no runtime service or root Compose container depends on MLflow.

## Phase 8 Knowledge Ingestion Path

```text
Controlled Markdown corpus
        |
        v
metadata validation + normalized parsing
        |
        v
heading-aware 400/60 model-tokenizer chunks
        |
        v
BAAI/bge-small-en-v1.5 (local CPU, normalized vector(384))
        |
        v
PostgreSQL rag schema
  +-- documents
  +-- chunks
  +-- ingestion_runs
```

The isolated `rag/ingestion` package and its Alembic history own this path.
Changed documents replace their chunks atomically, unchanged checksums are
skipped, and absent sources become inactive. The FastAPI RAG service remains
health-only.

## Phase 9 Offline Retrieval Path

```text
active rag.documents + rag.chunks
              |
              +--------------------+
              |                    |
              v                    v
     in-memory BM25         BGE query embedding
  title + heading + body           |
              |                    v
              |           exact pgvector cosine
              |                    |
              +---------+----------+
                        v
             reciprocal rank fusion
              candidate_k=20, k=60
                        |
                        v
       ranked chunks + offline benchmark reports
```

Both branches use the same fingerprinted active snapshot and filter semantics.
Primary evaluation is unfiltered and uses 50 manually authored queries with
section-level graded qrels. The package is offline; it does not alter the
health-only FastAPI service or Compose topology.

## Phase 10 Offline Diagnosis Path

```text
Phase 9 hybrid results (top 10)
              |
              v
pinned MiniLM cross-encoder on CPU
              |
              v
reranked top 5 evidence records [E1]...[E5]
              |
              v
grounded_incident_v1 + exact llama.cpp token budget
              |
              v
loopback Qwen3-4B-Q4_K_M (on demand)
              |
              v
Pydantic schema + server-side citation validation
              |
              v
grounded diagnosis OR insufficient_evidence
```

The reranker preserves BM25, dense, and RRF lineage. Generation uses no tools
and cannot execute recommendations. Retrieved content is delimited as untrusted
evidence, the GGUF must match its pinned checksum, and non-loopback inference
origins are rejected. The server is a developer-started local process rather
than a Compose service. Fake providers cover hosted CI without model downloads.

## Phase 11 Offline Quality Loop

```text
independent 40-case benchmark + curated gold
              |
              v
frozen Phase 10 retrieval, reranking, and generation
              |
              v
write-once gold-free final generation artifacts
              |
              +--> retrieval and citation metrics
              +--> pinned DeBERTa NLI support/completeness
              +--> BGE query/answer relevance proxy
              +--> abstention and adversarial checks
              +--> latency, determinism, and resource reports
              |
              v
ignored JSON/Markdown/CSV reports + empty manual-review fields
```

Gold data is evaluator-only. Adversarial overlays are injected after retrieval
as delimited untrusted evidence and never enter the corpus. Hosted CI validates
contracts with deterministic fakes and downloads no models. See
[`rag-evaluation.md`](rag-evaluation.md) for measured results and limitations.

## Phase 2 Streaming Path

```text
OpenTelemetry Demo
        |
        v
OpenTelemetry Collector
        |
        v
   telemetry.raw
        |
        v
Telemetry Worker
        |
        +----------------+
        |                |
        v                v
telemetry.processed  telemetry.dlq
```

The Phase 1 Collector-to-JSONL path remains available as an offline dataset
mode. Phase 2 adds a separate Collector-to-Kafka overlay and a replay producer
for those JSONL captures. The worker validates and wraps raw OTLP JSON but does
not perform feature engineering, inference, or incident creation.

## Logical Architecture

```text
                 React Dashboard
                        |
                        v
              Spring Boot Incident API
                        |
                        v
                 Kafka Event Backbone
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
     Telemetry        ML Service    RAG Service
      Service
          |             |             |
          +-------------+-------------+
                        |
                        v
               PostgreSQL + pgvector

                      Redis


                OpenTelemetry
                     |
                     v
                 Prometheus
                     |
                     v
                   Grafana
```

The diagram describes intended long-term logical relationships, not fully deployed Phase 11 infrastructure.

## Service Responsibilities

### Incident Service

The Phase 3 system of record for manually managed incident lifecycle, metadata,
severity, ownership, affected services, root cause, remediation, and chronological
timeline entries. It exposes REST endpoints and persists to PostgreSQL through
Spring Data JPA. Authentication, RBAC, Kafka-driven incident creation, and hard
deletion are not implemented.

### Telemetry Service

The entry point for future logs, metrics, traces, preprocessing, and feature generation. In Phase 2 its API remains health-only, while a separate worker consumes raw OTLP JSON from Kafka, validates it, emits processed envelopes, and routes invalid input to a DLQ. It does not create features or incidents.

### ML Service and offline ML workspace

The production ML service remains a health-only shell with no model dependency or
inference endpoint. The separate `ml/feature_engineering` workspace owns offline
OTLP normalization and Parquet contracts. Phase 5's `ml/anomaly_detection`
workspace owns the readiness gate, run split, fitted preprocessing, unsupervised
detectors, evaluation, and ignored artifacts. Phase 6's
`ml/incident_classification` workspace owns frozen anomaly adaptation,
service-independent run aggregation, supervised cross-validation, evaluation,
and ignored classifier artifacts. Phase 7's isolated `ml/model_lifecycle`
workspace owns local MLflow tracking, registry aliases, integrity verification,
promotion, rollback, and audit. Serving and online parity remain future work.

### RAG Service and offline ingestion workspace

The production RAG service remains a health-only shell with no model, retrieval,
or SLM dependency. Phase 8's separate `rag/ingestion` workspace owns the curated
runbook/postmortem corpus, validated metadata, deterministic chunks, local BGE
embeddings, ingestion manifests, and the PostgreSQL `rag` schema. Phase 9's
`rag/retrieval` workspace owns BM25, exact dense search, metadata filtering,
RRF, and offline evaluation. Phase 10's isolated `rag/reranking` workspace owns
the MiniLM boundary, lineage, evidence selection, and new frozen benchmark;
`rag/generation` owns the local llama.cpp provider, prompt, token budget,
structured diagnosis, citation validation, and abstention. None of these offline
concerns move into the API shell. Phase 11's isolated `rag/evaluation`
workspace owns the independent benchmark, frozen configuration identity,
write-once result artifacts, automated quality metrics, ablation, uncertainty,
failure analysis, and empty manual-review template.

## Future Design Constraints

### Event-driven system

Phase 2 implements `telemetry.raw`, `telemetry.processed`, and `telemetry.dlq` with versioned contracts, explicit partitions and retention, manual commits, bounded retries, deterministic event IDs, and documented at-least-once semantics. `anomaly.detected`, `incident.created`, `incident.updated`, `model.predictions`, and `rag.indexing` remain future topics. Production partitioning, scaling, security, and backpressure policies remain future work.

### Storage

PostgreSQL now provides relational incident persistence using Flyway-owned tables
and Phase 8 vector knowledge persistence using an Alembic-owned `rag` schema.
Compose uses a pinned PostgreSQL 18 pgvector image and the existing named volume.
Redis remains a future capability. The telemetry demo's separate PostgreSQL and
Valkey containers are isolated workload internals and are not AegisAI persistence.

### Incident lifecycle

The enforced transition graph is:

```text
OPEN ----------> INVESTIGATING -------> MITIGATED
 |                     ^                    |
 |                     +--------------------+
 |                     ^                    |
 +------> RESOLVED ----+                    |
             |                              |
             +----------> CLOSED            |
             ^                              |
             +------------------------------+
```

More precisely: `OPEN -> INVESTIGATING|RESOLVED`,
`INVESTIGATING -> MITIGATED|RESOLVED`,
`MITIGATED -> INVESTIGATING|RESOLVED`, and
`RESOLVED -> INVESTIGATING|CLOSED`. `CLOSED` is terminal.

### Machine learning

Phase 5 implements offline anomaly detection using a robust top-k deviation
baseline and Isolation Forest. Metric baselines, imputation, and detector fitting
use normal training runs only; selection and threshold calibration use validation;
the final report uses an untouched test split. Phase 6 adds offline five-class
incident classification from frozen anomaly-ranked context, comparing Logistic
Regression and Random Forest with fold-local preprocessing and an untouched
run-level final test. Phase 7 adds local MLflow 3.17 tracking, SQLite registry
metadata, dataset/model integrity hashes, and candidate/champion lifecycle over
those frozen outputs. Later phases may add serving and drift monitoring.

### Retrieval-augmented generation

Phase 8 implements controlled source ingestion, local dense embeddings, and
pgvector storage. Phase 9 adds evaluated BM25, exact dense retrieval, and fixed
reciprocal-rank fusion. Phase 10 adds pinned cross-encoder reranking and an
offline, structured, citation-validated local SLM path. Phase 11 adds formal
offline answer-quality and faithfulness proxies without tuning that path. A
production retrieval/diagnosis API, human evaluation, and remote LLM providers
remain future work.

### Observability

OpenTelemetry will provide instrumentation and distributed tracing, Prometheus will collect metrics, Grafana will visualize operational signals, and services will emit structured logs. Phase 2 uses the external instrumented demo as a telemetry source for offline capture or Kafka streaming; it does not deploy an AegisAI production observability pipeline.

### Cloud delivery

The intended portfolio delivery path is:

```text
GitHub Actions
      |
      v
AWS IAM OIDC
      |
      v
Amazon ECR
      |
      v
EC2
      |
      v
Docker Compose
```

AWS resources, deployment automation, and credentials are outside Phase 11.
