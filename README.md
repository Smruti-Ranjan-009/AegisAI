# AegisAI — Distributed Incident Intelligence Platform

AI-powered incident intelligence platform combining ML-based anomaly detection, hybrid RAG, and event-driven microservices to diagnose distributed-system failures and generate grounded remediation recommendations.

> **Current status: Phase 3 — Incident Management and PostgreSQL Persistence**

## Overview

AegisAI is a production-style portfolio project for exploring incident intelligence across Java, Python, event-driven systems, machine learning, retrieval-augmented generation, observability, and cloud deployment. Phase 3 preserves the Phase 2 telemetry pipeline and adds a PostgreSQL-backed incident-management API with explicit lifecycle rules, timeline history, Flyway migrations, transaction boundaries, and optimistic locking.

## Problem Statement

Distributed-system incidents generate fragmented logs, metrics, traces, operational knowledge, and ownership data. The long-term goal is to correlate those signals, identify abnormal behavior, organize incident response, and produce evidence-grounded remediation guidance. Phase 3 supports manual incident management only; telemetry does not create incidents automatically and no ML or AI analysis is implemented.

## Long-Term Architecture

The planned system consists of a React dashboard, a Spring Boot incident API, three focused Python services, Kafka-based communication, PostgreSQL with pgvector, Redis, and an OpenTelemetry/Prometheus/Grafana observability stack. See [docs/architecture.md](docs/architecture.md) for the planned responsibilities and constraints.

## Technology Stack

| Area | Implemented | Planned later |
| --- | --- | --- |
| Incident API | Java 17, Spring Boot 3.4, REST, Validation, Spring Data JPA, Flyway | Kafka integration, authentication, RBAC |
| Python services | Python 3.12, FastAPI, Pydantic, Uvicorn; telemetry worker uses `confluent-kafka` and JSON Schema | ML and RAG-specific libraries |
| Dataset laboratory | OpenTelemetry Demo 3.1.0, Collector file exporter, stdlib Python CLI | Feature engineering |
| Event backbone | Apache Kafka 4.3.1 in single-node KRaft mode; raw, processed, and DLQ topics | Multi-node or managed production Kafka |
| Testing and quality | JUnit, Spring Boot Test, Testcontainers PostgreSQL, pytest, Ruff, Kafka integration tests | Broader end-to-end suites |
| Containers | Docker, Docker Compose | Production orchestration and cloud delivery |
| Data and messaging | PostgreSQL 18.4 with persistent local volume; Kafka with a persistent local volume | pgvector, Redis |
| Observability | OpenTelemetry Demo is a telemetry source only | AegisAI OpenTelemetry, Prometheus, Grafana pipelines |
| Frontend | Directory placeholder only | React dashboard |

## Repository Structure

```text
services/       Independently buildable backend services
frontend/       Future React application
shared/         Versioned event contracts and future shared schemas
ml/             Future offline ML workspaces
rag/            Future RAG pipelines and evaluation
infrastructure/ Docker foundations and the isolated telemetry lab
data/           Raw capture location and future curated samples
tests/          Cross-service and Kafka integration tests
docs/           Architecture and project documentation
scripts/        Telemetry-lab and Kafka pipeline CLIs
```

Each Python service owns its dependencies; there is intentionally no root `requirements.txt`.

## Current Implementation Status

Phase 3 includes the four service foundations, the Phase 1 offline dataset laboratory, the Phase 2 Kafka telemetry pipeline, and manual incident management backed by PostgreSQL. The incident API supports create, retrieve, filtered/paginated list, controlled updates, lifecycle transitions, and chronological timeline notes. Flyway owns the schema; Hibernate validates it; Testcontainers exercises the real PostgreSQL engine.

Phase 3 does **not** include automated Kafka-to-incident creation, feature engineering, ML models, anomaly detection, classification, RAG, LLM investigation, Redis, pgvector, AWS deployment, production observability, authentication, RBAC, or a frontend.

The implementation journals are [decisions.md](decisions.md), [flow.md](flow.md), and [features.md](features.md). Future phases should read these before changing established behavior.

## Prerequisites

- JDK 17 with `JAVA_HOME` configured
- Python 3.12 (a Conda environment is supported)
- Docker Desktop with Docker Compose, for container validation
- Git

Maven does not need to be installed globally; the incident service includes the Maven Wrapper.

## Local Development

Clone the repository and optionally copy the safe example environment file:

```powershell
Copy-Item .env.example .env
```

The defaults are development-only values sufficient for local Phase 3 use. `.env` is ignored and must never contain committed secrets.

Start PostgreSQL before running the incident service directly:

```powershell
docker compose up -d --wait postgres
```

The database is available at `localhost:5432` by default. Override connection values through `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.

## Telemetry Dataset Lab

The lab clones the official OpenTelemetry Demo into ignored runtime storage, verifies tag `3.1.0` and its exact commit, and starts only upstream `compose.yaml` plus AegisAI's capture overlay under the isolated `aegis-telemetry-lab` Compose project. The upstream demo's own PostgreSQL and Valkey containers are workload internals, not AegisAI persistence.

```powershell
conda activate aegis
python scripts\telemetry_lab.py setup
python scripts\telemetry_lab.py scenarios
python scripts\telemetry_lab.py start
python scripts\telemetry_lab.py run --scenario normal --warmup 20 --duration 60
python scripts\telemetry_lab.py run --scenario cpu_saturation --warmup 20 --duration 60
python scripts\telemetry_lab.py stop
```

Captures are written to ignored directories under `data/raw/<run-id>/`. See [docs/telemetry-dataset.md](docs/telemetry-dataset.md) for the data contract, validation behavior, resource notes, and cleanup commands. The CLI uses only Python's standard library; the Java service does not run inside Conda.

## Kafka Telemetry Pipeline

Install the telemetry-service dependencies, then start Kafka, deterministic
topic provisioning, and the worker:

```powershell
conda activate aegis
python -m pip install -r services\telemetry-service\requirements.txt
python scripts\kafka_pipeline.py start
python scripts\kafka_pipeline.py topics
```

Replay a validated Phase 1 run or start the separate live streaming overlay:

```powershell
python scripts\kafka_pipeline.py replay --run <run-id>
python scripts\kafka_pipeline.py consume --topic telemetry.processed --limit 5

python scripts\kafka_pipeline.py stream-start
python scripts\kafka_pipeline.py stream-status
python scripts\kafka_pipeline.py stream-stop
```

Stop Kafka while preserving its named data volume:

```powershell
python scripts\kafka_pipeline.py stop
```

See [docs/kafka-pipeline.md](docs/kafka-pipeline.md) for topic settings,
delivery semantics, contracts, DLQ behavior, cleanup, and troubleshooting. The
helper checks Docker availability but never starts Docker Desktop itself.

## Python Environment Setup

If an existing Conda environment is used:

```powershell
conda activate aegis
```

Install dependencies independently for each service. A separate virtual environment per service is recommended when dependencies begin to diverge:

```powershell
cd services\telemetry-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Repeat for `ml-service` and `rag-service`. The Java service does not run inside Conda and uses JDK 17, `JAVA_HOME`, and the Maven Wrapper.

## Running Individual Services

Incident service:

```powershell
docker compose up -d --wait postgres
cd services\incident-service
.\mvnw.cmd spring-boot:run
```

Each Python service is run from its own directory after installing that service's dependencies:

```powershell
cd services\telemetry-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

cd ..\ml-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002

cd ..\rag-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003
```

## Running Tests

```powershell
cd services\incident-service
.\mvnw.cmd test

cd ..\telemetry-service
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .

cd ..\ml-service
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .

cd ..\rag-service
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .

cd ..\..
$env:KAFKA_INTEGRATION = "1"
python -m pytest tests\integration -m kafka_integration
```

The Java suite requires Docker because its context, API, migration, transaction,
and optimistic-locking tests use Testcontainers PostgreSQL. The Kafka integration
suite expects the Phase 2 Compose services to be running; CI configures both paths.

## Running with Docker Compose

From the repository root:

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose down
```

Compose starts PostgreSQL, the four backend APIs, Kafka, one-shot topic provisioning,
and the separate telemetry worker. It does not start Redis, pgvector, Prometheus,
Grafana, the OpenTelemetry Demo, or a frontend container.

Normal shutdown preserves both named data volumes:

```powershell
docker compose down
```

To intentionally reset all local Kafka and PostgreSQL data:

```powershell
docker compose down -v
```

The PostgreSQL volume is named `aegis-postgres-data`. See
[docs/incident-api.md](docs/incident-api.md) for API examples, lifecycle rules,
error semantics, and persistence verification. The relational schema, indexes,
migrations, and volume behavior are documented in [docs/database.md](docs/database.md).

## Health Endpoints

| Service | Endpoint |
| --- | --- |
| Incident | `http://localhost:8080/api/v1/health` |
| Incident Actuator | `http://localhost:8080/actuator/health` |
| Telemetry | `http://localhost:8001/health` |
| ML | `http://localhost:8002/health` |
| RAG | `http://localhost:8003/health` |

PowerShell verification:

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/health
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8003/health
```

## Planned Development Phases

1. Phase 0: repository and service foundation (complete)
2. Phase 1: telemetry generation and raw dataset capture (complete)
3. Phase 2: Kafka event backbone and telemetry streaming pipeline (complete)
4. Phase 3: incident management backend and PostgreSQL persistence (current)
5. Phase 4 and later: feature engineering, ML, RAG, frontend, production observability, CI/CD, and AWS delivery

Each later capability will be introduced as a separate scoped phase.

## Security / Secrets Guidance

- Commit only `.env.example`, never `.env`.
- Do not put passwords, API keys, cloud credentials, or tokens in source code or images.
- Use environment variables locally and a managed secret store for future deployments.
- Treat values in `.env.example` as non-production placeholders.

## Future Deployment Strategy

The planned portfolio deployment path is GitHub Actions to AWS IAM OIDC,
Amazon ECR, an EC2 host, and Docker Compose. Phase 3 contains no AWS resources,
deployment workflows, credentials, or production infrastructure.
