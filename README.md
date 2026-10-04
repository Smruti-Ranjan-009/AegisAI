# AegisAI — Distributed Incident Intelligence Platform

AI-powered incident intelligence platform combining ML-based anomaly detection, hybrid RAG, and event-driven microservices to diagnose distributed-system failures and generate grounded remediation recommendations.

> **Current status: Phase 0 — Foundation**

## Overview

AegisAI is a production-style portfolio project for exploring incident intelligence across Java, Python, event-driven systems, machine learning, retrieval-augmented generation, observability, and cloud deployment. Phase 0 deliberately provides only runnable service shells, health checks, tests, container images, and documentation.

## Problem Statement

Distributed-system incidents generate fragmented logs, metrics, traces, operational knowledge, and ownership data. The long-term goal is to correlate those signals, identify abnormal behavior, organize incident response, and produce evidence-grounded remediation guidance. None of that business functionality is implemented in Phase 0.

## Long-Term Architecture

The planned system consists of a React dashboard, a Spring Boot incident API, three focused Python services, Kafka-based communication, PostgreSQL with pgvector, Redis, and an OpenTelemetry/Prometheus/Grafana observability stack. See [docs/architecture.md](docs/architecture.md) for the planned responsibilities and constraints.

## Technology Stack

| Area | Phase 0 | Planned later |
| --- | --- | --- |
| Incident API | Java 17, Spring Boot, Maven | PostgreSQL persistence, Kafka, RBAC |
| Python services | Python 3.12, FastAPI, Pydantic, Uvicorn | Telemetry, ML, and RAG-specific libraries |
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
infrastructure/ Future Docker, AWS, Prometheus, and Grafana assets
tests/          Future cross-service integration and e2e suites
docs/           Architecture and project documentation
scripts/        Future developer and automation scripts
```

Each Python service owns its dependencies; there is intentionally no root `requirements.txt`.

## Current Implementation Status

Phase 0 includes four minimal services, deterministic health responses, unit/slice tests, lint configuration, container definitions, and local orchestration. It does **not** include ML models, anomaly detection, classification, RAG, LLM investigation, Kafka, Redis, production PostgreSQL persistence, AWS deployment, OpenTelemetry, Prometheus, or Grafana.

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

1. Phase 0: repository and service foundation (current)
2. Telemetry generation and ingestion foundations
3. Kafka event backbone and event contracts
4. Incident lifecycle and PostgreSQL persistence
5. Feature engineering, anomaly detection, and classification
6. Model tracking and drift monitoring
7. RAG ingestion, hybrid retrieval, reranking, and evaluation
8. Frontend experience and end-to-end workflows
9. Observability, CI/CD expansion, and AWS deployment

Each later capability will be introduced as a separate scoped phase.

## Security / Secrets Guidance

- Commit only `.env.example`, never `.env`.
- Do not put passwords, API keys, cloud credentials, or tokens in source code or images.
- Use environment variables locally and a managed secret store for future deployments.
- Treat values in `.env.example` as non-production placeholders.

## Future Deployment Strategy

The planned portfolio deployment path is GitHub Actions to AWS IAM OIDC, Amazon ECR, an EC2 host, and Docker Compose. Phase 0 contains no AWS resources, deployment workflows, credentials, or production infrastructure.
