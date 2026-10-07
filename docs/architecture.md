# Planned Architecture

Phase 6 preserves the operational service, incident, Kafka, feature, and frozen anomaly paths, then adds reproducible offline five-class incident classification over a validated synthetic-fault campaign. Automated telemetry-to-incident integration, model serving, RAG, production observability, frontend, and cloud capabilities remain future design goals.

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
PostgreSQL 18.4
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

The diagram describes intended long-term logical relationships, not fully deployed Phase 6 infrastructure.

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
and ignored classifier artifacts. Serving and online parity remain future work.

### RAG Service

The future knowledge service for runbooks, postmortems, incident history, architecture documents, hybrid retrieval, reranking, and grounded LLM generation. In Phase 0 it exposes only a health endpoint and has no retrieval or LLM dependencies.

## Future Design Constraints

### Event-driven system

Phase 2 implements `telemetry.raw`, `telemetry.processed`, and `telemetry.dlq` with versioned contracts, explicit partitions and retention, manual commits, bounded retries, deterministic event IDs, and documented at-least-once semantics. `anomaly.detected`, `incident.created`, `incident.updated`, `model.predictions`, and `rag.indexing` remain future topics. Production partitioning, scaling, security, and backpressure policies remain future work.

### Storage

PostgreSQL now provides relational incident persistence using normalized tables,
constraints, indexes, Flyway migrations, and a named Compose volume. pgvector and
Redis remain future capabilities. The telemetry demo's separate PostgreSQL and
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
run-level final test. Later phases will cover MLflow-based lifecycle management,
serving, and drift monitoring.

### Retrieval-augmented generation

Later phases will evaluate BM25, dense retrieval, reciprocal rank fusion, reranking, citations, grounded generation, and RAG quality. No vector database, embedding model, LLM SDK, or prompt orchestration is included now.

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

AWS resources, deployment automation, and credentials are outside Phase 6.
