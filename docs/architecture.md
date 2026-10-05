# Planned Architecture

Phase 1 preserves the four service foundations and adds an offline telemetry dataset laboratory. The long-term data, messaging, intelligence, production observability, frontend, and cloud capabilities below remain future design goals.

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

This isolated path uses the demo's built-in traffic generator and deterministic feature flags. It exists only to generate validated local experiment files. The file exporter is not the intended production architecture, and the Phase 0 telemetry-service is not in this capture path. Phase 2 will introduce the separate AegisAI Kafka event pipeline.

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

The diagram describes intended long-term logical relationships, not deployed Phase 1 infrastructure.

## Planned Service Responsibilities

### Incident Service

The future system of record for incident lifecycle, metadata, severity, ownership, APIs, RBAC, and persistence. In Phase 0 it exposes only application and Actuator health endpoints and uses an in-memory H2 datasource so local startup has no external dependency.

### Telemetry Service

The future entry point for logs, metrics, traces, preprocessing, feature generation, and Kafka ingestion. It still exposes only its Phase 0 health endpoint; the Phase 1 external demo writes directly through its own Collector to offline files.

### ML Service

The future home for anomaly detection, incident classification, inference, model versioning, and ML monitoring. In Phase 0 it exposes only a health endpoint and has no ML dependencies or artifacts.

### RAG Service

The future knowledge service for runbooks, postmortems, incident history, architecture documents, hybrid retrieval, reranking, and grounded LLM generation. In Phase 0 it exposes only a health endpoint and has no retrieval or LLM dependencies.

## Future Design Constraints

### Event-driven system

Kafka is planned to carry `telemetry.raw`, `telemetry.processed`, `anomaly.detected`, `incident.created`, `incident.updated`, `model.predictions`, and `rag.indexing` events. Contracts will be versioned under `shared/`. Consumer groups, partitioning, retries, dead-letter queues, idempotency, and backpressure must be designed before workflows are implemented.

### Storage

PostgreSQL will provide relational persistence, pgvector will support vector search, and Redis will support carefully selected cache or ephemeral coordination use cases. AegisAI does not start or connect to these systems in its default Compose configuration. The telemetry demo's PostgreSQL and Valkey containers are isolated workload internals, not this future architecture.

### Machine learning

Later phases will cover feature engineering, anomaly detection, incident classification, MLflow-based lifecycle management, and drift monitoring. Training code and model binaries are intentionally absent now.

### Retrieval-augmented generation

Later phases will evaluate BM25, dense retrieval, reciprocal rank fusion, reranking, citations, grounded generation, and RAG quality. No vector database, embedding model, LLM SDK, or prompt orchestration is included now.

### Observability

OpenTelemetry will provide instrumentation and distributed tracing, Prometheus will collect metrics, Grafana will visualize operational signals, and services will emit structured logs. Phase 1 uses an external instrumented demo and file exporter only; it does not deploy an AegisAI production observability pipeline.

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

AWS resources, deployment automation, and credentials are outside Phase 0.
