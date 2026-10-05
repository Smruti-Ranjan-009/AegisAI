# AegisAI — Distributed Incident Intelligence Platform

AI-powered incident intelligence platform combining ML-based anomaly detection, hybrid RAG, and event-driven microservices to diagnose distributed-system failures and generate grounded remediation recommendations.

> **Current status: Phase 1 — Telemetry Generation and Dataset Capture**

## Overview

AegisAI is a production-style portfolio project for exploring incident intelligence across Java, Python, event-driven systems, machine learning, retrieval-augmented generation, observability, and cloud deployment. Phase 1 preserves the Phase 0 service foundation and adds an isolated, reproducible laboratory for generating labeled raw metrics, logs, and traces.

## Problem Statement

Distributed-system incidents generate fragmented logs, metrics, traces, operational knowledge, and ownership data. The long-term goal is to correlate those signals, identify abnormal behavior, organize incident response, and produce evidence-grounded remediation guidance. Phase 1 creates raw, labeled experiment data only; it does not perform feature engineering, detection, incident management, or AI analysis.

## Long-Term Architecture

The planned system consists of a React dashboard, a Spring Boot incident API, three focused Python services, Kafka-based communication, PostgreSQL with pgvector, Redis, and an OpenTelemetry/Prometheus/Grafana observability stack. See [docs/architecture.md](docs/architecture.md) for the planned responsibilities and constraints.

## Technology Stack

| Area | Implemented | Planned later |
| --- | --- | --- |
| Incident API | Phase 0: Java 17, Spring Boot, Maven | PostgreSQL persistence, Kafka, RBAC |
| Python services | Phase 0: Python 3.12, FastAPI, Pydantic, Uvicorn | Telemetry, ML, and RAG-specific libraries |
| Dataset laboratory | OpenTelemetry Demo 3.1.0, Collector file exporter, stdlib Python CLI | Streaming ingestion and feature engineering |
| Testing and quality | JUnit/Spring Boot Test, pytest, Ruff | Integration and end-to-end suites |
| Containers | Docker, Docker Compose | Production orchestration and cloud delivery |
| Data and messaging | H2 for local Java startup only | PostgreSQL, pgvector, Redis, Kafka |
| Observability | Not implemented | OpenTelemetry, Prometheus, Grafana |
| Frontend | Directory placeholder only | React dashboard |

## Repository Structure

```text
services/       Independently buildable backend services
frontend/       Future React application
shared/         Future cross-service contracts and schemas
ml/             Future offline ML workspaces
rag/            Future RAG pipelines and evaluation
infrastructure/ Docker foundations and the isolated telemetry lab
data/           Raw capture location and future curated samples
tests/          Cross-service placeholders and telemetry-lab unit tests
docs/           Architecture and project documentation
scripts/        Telemetry-lab orchestration CLI
```

Each Python service owns its dependencies; there is intentionally no root `requirements.txt`.

## Current Implementation Status

Phase 1 includes the four Phase 0 services plus a local offline dataset-generation path based on the official OpenTelemetry Demo 3.1.0. It produces separate OTLP JSONL signal files and a ground-truth manifest for normal or controlled-fault runs. It does **not** include feature engineering, ML models, anomaly detection, classification, RAG, LLM investigation, Kafka, AegisAI Redis/PostgreSQL persistence, AWS deployment, Prometheus, Grafana, or production incident workflows.

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

The defaults are sufficient for Phase 0. `.env` is ignored and must never contain committed secrets.

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
```

## Running with Docker Compose

From the repository root:

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose down
```

Compose starts only the four Phase 0 backend services. It does not start infrastructure dependencies.

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
2. Phase 1: telemetry generation and raw dataset capture (current)
3. Phase 2: Kafka event backbone and event contracts
4. Later phases: incident persistence, feature engineering, ML, RAG, frontend, production observability, CI/CD, and AWS delivery

Each later capability will be introduced as a separate scoped phase.

## Security / Secrets Guidance

- Commit only `.env.example`, never `.env`.
- Do not put passwords, API keys, cloud credentials, or tokens in source code or images.
- Use environment variables locally and a managed secret store for future deployments.
- Treat values in `.env.example` as non-production placeholders.

## Future Deployment Strategy

The planned portfolio deployment path is GitHub Actions to AWS IAM OIDC, Amazon ECR, an EC2 host, and Docker Compose. Phase 1 contains no AWS resources, deployment workflows, credentials, or production infrastructure.
