# Planned Architecture

Phase 3 preserves the service foundations, offline telemetry dataset laboratory, and Kafka telemetry path, then adds manual incident management backed by PostgreSQL. Automated telemetry-to-incident integration, intelligence, production observability, frontend, and cloud capabilities remain future design goals.

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
  +-- incident_timeline
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

The diagram describes intended long-term logical relationships, not fully deployed Phase 3 infrastructure.

## Service Responsibilities

### Incident Service

The Phase 3 system of record for manually managed incident lifecycle, metadata,
severity, ownership, affected services, root cause, remediation, and chronological
timeline entries. It exposes REST endpoints and persists to PostgreSQL through
Spring Data JPA. Authentication, RBAC, Kafka-driven incident creation, and hard
deletion are not implemented.

### Telemetry Service

The entry point for future logs, metrics, traces, preprocessing, and feature generation. In Phase 2 its API remains health-only, while a separate worker consumes raw OTLP JSON from Kafka, validates it, emits processed envelopes, and routes invalid input to a DLQ. It does not create features or incidents.

### ML Service

The future home for anomaly detection, incident classification, inference, model versioning, and ML monitoring. In Phase 0 it exposes only a health endpoint and has no ML dependencies or artifacts.

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

Later phases will cover feature engineering, anomaly detection, incident classification, MLflow-based lifecycle management, and drift monitoring. Training code and model binaries are intentionally absent now.

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

AWS resources, deployment automation, and credentials are outside Phase 3.
