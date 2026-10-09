# AegisAI — Distributed Incident Intelligence Platform

AI-powered incident intelligence platform combining ML-based anomaly detection, hybrid RAG, and event-driven microservices to diagnose distributed-system failures and generate grounded remediation recommendations.

> **Current status: Phase 10 — Cross-Encoder Reranking and Local Grounded Generation**

## Overview

AegisAI is a production-style portfolio project for exploring incident intelligence across Java, Python, event-driven systems, machine learning, retrieval-augmented generation, observability, and cloud deployment. Phase 10 adds pinned CPU cross-encoder reranking and structured, citation-validated generation through an on-demand local quantized SLM. The production RAG API remains health-only.

## Problem Statement

Distributed-system incidents generate fragmented logs, metrics, traces, operational knowledge, and ownership data. The long-term goal is to correlate those signals, identify abnormal behavior, organize incident response, and produce evidence-grounded remediation guidance. Phase 10 provides a local, advisory offline diagnosis path with strict evidence and abstention contracts; it does not automate remediation or expose a production endpoint.

## Long-Term Architecture

The planned system consists of a React dashboard, a Spring Boot incident API, three focused Python services, Kafka-based communication, PostgreSQL with pgvector, Redis, and an OpenTelemetry/Prometheus/Grafana observability stack. See [docs/architecture.md](docs/architecture.md) for the planned responsibilities and constraints.

## Technology Stack

| Area | Implemented | Planned later |
| --- | --- | --- |
| Incident API | Java 17, Spring Boot 3.4, REST, Validation, Spring Data JPA, Flyway | Kafka integration, authentication, RBAC |
| Python services | Python 3.12 FastAPI shells and telemetry worker; isolated ingestion package | RAG serving dependencies |
| Dataset and ML | OpenTelemetry Demo 3.1.0 captures; protobuf OTLP normalization; PyArrow Parquet; deterministic UTC windows; frozen anomaly detection and incident classification; MLflow 3.17 tracking and alias-based registry lifecycle | Model serving and drift monitoring |
| Event backbone | Apache Kafka 4.3.1 in single-node KRaft mode; raw, processed, and DLQ topics | Multi-node or managed production Kafka |
| Testing and quality | JUnit, Spring Boot Test, Testcontainers PostgreSQL, pytest, Ruff, Kafka integration tests | Broader end-to-end suites |
| Containers | Docker, Docker Compose | Production orchestration and cloud delivery |
| Data and messaging | PostgreSQL 18.6 with pgvector 0.8.6; persistent PostgreSQL and Kafka volumes | Redis |
| Observability | OpenTelemetry Demo is a telemetry source only | AegisAI OpenTelemetry, Prometheus, Grafana pipelines |
| Frontend | Directory placeholder only | React dashboard |

## Repository Structure

```text
services/       Independently buildable backend services
frontend/       Future React application
shared/         Versioned event contracts and future shared schemas
ml/             Installable feature-engineering, anomaly, and classification packages
rag/            Knowledge ingestion, retrieval, reranking, generation, and evaluation assets
infrastructure/ Docker foundations and the isolated telemetry lab
data/           Raw capture location and future curated samples
tests/          Cross-service and Kafka integration tests
docs/           Architecture and project documentation
scripts/        Telemetry-lab and Kafka pipeline CLIs
```

Each Python service owns its dependencies; there is intentionally no root `requirements.txt`.

## Current Implementation Status

Phase 10 includes all Phase 0–9 capabilities plus isolated `rag/reranking` and
`rag/generation` packages. A pinned MiniLM cross-encoder reranks ten hybrid
candidates into five evidence records. An on-demand loopback llama.cpp server
hosts a checksum-verified Qwen3 4B Q4_K_M model and returns a strict structured
diagnosis whose citations are independently validated and reconstructed from
the evidence map. Python Alembic continues to own only the `rag` schema; Spring
Flyway remains unchanged.

The implemented offline path is: telemetry → anomaly detection → abnormal
context aggregation → five-class incident prediction → MLflow tracking → model
registry lifecycle. Phase 5 results remain in
[docs/anomaly-detection.md](docs/anomaly-detection.md); Phase 6 methodology,
measured results, and limitations are in
[docs/incident-classification.md](docs/incident-classification.md); Phase 7 is in
[docs/model-lifecycle.md](docs/model-lifecycle.md).

Phase 10 does **not** include a production diagnosis API, permanent model
server, formal generation-quality evaluation, automated remediation,
Kafka-to-incident creation, Redis, AWS deployment, production observability,
authentication, RBAC, or a frontend. The production `rag-service` and
`ml-service` remain health-only.

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

The defaults are development-only values sufficient for the local stack. `.env` is ignored and must never contain committed secrets.

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

## Offline Feature Engineering

Install Phase 4 independently; its columnar and OTLP dependencies are not added
to any production service:

```powershell
conda activate aegis
python -m pip install -e "ml\feature_engineering[test]"

python -m aegis_features.cli inspect --run <run-id>
python -m aegis_features.cli build --run <normal-run-id> --run <fault-run-id> --window-seconds 60
python -m aegis_features.cli validate --dataset <dataset-id>
python -m aegis_features.cli summary --dataset <dataset-id>
```

The pipeline is raw OTLP JSON → typed observations → event-time service windows
→ model-ready Parquet features. Generated datasets under `data/features/` are
ignored. See [docs/feature-engineering.md](docs/feature-engineering.md), the
[telemetry inventory](docs/telemetry-feature-inventory.md), and the versioned
[ML contracts](shared/contracts/ml/service-window-features-v1.md).

## Offline Anomaly Detection

Install the independent Phase 5 package after building a feature dataset from
the accepted `anomaly-v1` campaign runs:

```powershell
conda activate aegis
python -m pip install -e "ml\anomaly_detection[test]"

python scripts\telemetry_lab.py campaign --plan anomaly-v1
python -m aegis_anomaly.cli readiness --dataset <dataset-id>
python -m aegis_anomaly.cli train --dataset <dataset-id>
python -m aegis_anomaly.cli evaluate --model <model-id>
python -m aegis_anomaly.cli score --model <model-id> --dataset <dataset-id>
```

Training is offline and refuses fewer than six normal runs, two runs per fault
scenario, or 150 eligible normal service windows. Artifacts under
`artifacts/anomaly_detection/` and raw campaign captures remain ignored. See
[docs/anomaly-detection.md](docs/anomaly-detection.md) for label semantics,
leakage controls, metric baselines, evaluation, and trusted-artifact guidance.

## Offline Incident Classification

Install Phase 5 and Phase 6 independently, then build one classification row
per accepted fault run:

```powershell
conda activate aegis
python -m pip install -e "ml\anomaly_detection[test]"
python -m pip install -e "ml\incident_classification[test]"

python scripts\telemetry_lab.py campaign --plan classification-v1
python -m aegis_classifier.cli anomaly-score --feature-dataset <phase4-dataset-id>
python -m aegis_classifier.cli build --feature-dataset <phase4-dataset-id>
python -m aegis_classifier.cli readiness --dataset <classification-dataset-id>
python -m aegis_classifier.cli train --dataset <classification-dataset-id>
python -m aegis_classifier.cli evaluate --model <classifier-model-id>
python -m aegis_classifier.cli score --model <classifier-model-id> --dataset <classification-dataset-id>
```

`normal` is not a classification class. The classifier runs only after the
frozen anomaly stage and never encodes service identity. Generated datasets and
artifacts remain ignored. See
[docs/incident-classification.md](docs/incident-classification.md).

## Local Model Lifecycle

Install the isolated Phase 7 package alongside the two trusted model packages.
The commands import existing artifacts; they do not retrain them:

```powershell
conda activate aegis
python -m pip install -e "ml\anomaly_detection"
python -m pip install -e "ml\incident_classification"
python -m pip install -e "ml\model_lifecycle[test]"

python -m aegis_lifecycle.cli --json init
python -m aegis_lifecycle.cli --json import-anomaly --model-id anomaly-v1-4c84405c580f
python -m aegis_lifecycle.cli --json import-classifier --model-id classifier-v1-d37b9861572f
python -m aegis_lifecycle.cli --json audit
python -m aegis_lifecycle.cli --json verify --model anomaly --alias champion
python -m aegis_lifecycle.cli --json verify --model classifier --alias champion
```

The default SQLite database and MLflow artifact store are under ignored
`.runtime/mlflow/`. The optional UI binds to `127.0.0.1:5000`; it is not part of
Docker Compose. See [docs/model-lifecycle.md](docs/model-lifecycle.md) and the
permanent [decisions](decisions.md), [flows](flow.md), and
[feature/bug journal](features.md).

## Knowledge Ingestion

Install the isolated Phase 8 package. The `embeddings` extra is needed only for
real local BGE validation and ingestion:

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[test,embeddings]"
docker compose up -d --wait postgres
python -m aegis_rag_ingestion inspect --json
python -m aegis_rag_ingestion migrate --json
python -m aegis_rag_ingestion embed-validate --json
python -m aegis_rag_ingestion ingest --json
python -m aegis_rag_ingestion validate --smoke-query "high CPU saturation" --json
```

Run `ingest` a second time to verify idempotency. Generated manifests, reports,
and model caches belong under ignored `.runtime/`. See
[docs/rag-ingestion.md](docs/rag-ingestion.md) for metadata, schema, failure,
volume, and test details.

## Hybrid Retrieval

Install the ingestion package first because Phase 9 deliberately reuses its
frozen embedding and database contracts, then install the retrieval package:

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[embeddings]"
python -m pip install -e ".\rag\retrieval[test]"
docker compose up -d --wait postgres
python -m aegis_rag_retrieval validate-benchmark --json
python -m aegis_rag_retrieval search "PostgreSQL connection pool exhausted" --method hybrid --top-k 5 --json
python -m aegis_rag_retrieval filter-evaluate --json
python -m pytest rag\retrieval\tests -q --basetemp=.runtime\pytest-phase9
python -m ruff check rag\retrieval
```

Generated benchmark reports remain under ignored `.runtime/rag/retrieval/`.
See [docs/hybrid-retrieval.md](docs/hybrid-retrieval.md) for the retrieval
contract, benchmark methodology, measured results, and limitations.

## Reranking and Local Grounded Generation

Install the two Phase 10 packages after their Phase 8/9 dependencies. The model
extra is local-only; hosted CI uses deterministic fakes and downloads no model:

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[embeddings]"
python -m pip install -e ".\rag\retrieval"
python -m pip install -e ".\rag\reranking[test,models]"
python -m pip install -e ".\rag\generation[test]"
docker compose up -d --wait postgres
python -m aegis_rag_reranking validate-benchmark --json
python -m aegis_rag_reranking search --query "database connection pool exhaustion" --json
python -m aegis_rag_generation verify-model --json
python -m aegis_rag_generation model-health --json
python -m aegis_rag_generation diagnose --query "Why is checkout latency high?" --json
```

The real local Qwen command, pinned checksums, one-time reranking results,
functional smoke results, security model, and resource measurements are in
[docs/reranking-and-grounded-generation.md](docs/reranking-and-grounded-generation.md).
The llama.cpp server is on-demand, loopback-only, and not part of Compose.

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
python -m pip install -e "ml\feature_engineering[test]"
python -m pytest ml\feature_engineering\tests
python -m ruff check ml\feature_engineering

python -m pip install -e "ml\anomaly_detection[test]"
python -m pytest ml\anomaly_detection\tests
python -m ruff check ml\anomaly_detection

python -m pip install -e "ml\incident_classification[test]"
python -m pytest ml\incident_classification\tests
python -m ruff check ml\incident_classification

python -m pip install -e "ml\model_lifecycle[test]"
python -m pytest ml\model_lifecycle\tests
python -m ruff check ml\model_lifecycle

python -m pip install -e ".\rag\ingestion[test]"
python -m pytest rag\ingestion\tests -q --basetemp=.runtime\pytest-phase8
python -m ruff check rag\ingestion

python -m pip install -e ".\rag\retrieval[test]"
python -m pytest rag\retrieval\tests -q --basetemp=.runtime\pytest-phase9
python -m ruff check rag\retrieval

python -m pip install -e ".\rag\reranking[test]"
python -m pytest rag\reranking\tests -q --basetemp=.runtime\pytest-phase10-reranking
python -m ruff check rag\reranking

python -m pip install -e ".\rag\generation[test]"
python -m pytest rag\generation\tests -q --basetemp=.runtime\pytest-phase10-generation
python -m ruff check rag\generation

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

Compose starts PostgreSQL with pgvector, the four backend APIs, Kafka, one-shot
topic provisioning, and the separate telemetry worker. It does not start Redis,
Prometheus, Grafana, the OpenTelemetry Demo, a model server, or a frontend container.

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
4. Phase 3: incident management backend and PostgreSQL persistence (complete)
5. Phase 4: ML feature engineering (complete)
6. Phase 5: anomaly detection (complete)
7. Phase 6: incident classification (complete)
8. Phase 7: MLflow experiment tracking and model lifecycle (complete)
9. Phase 8: RAG ingestion and vector knowledge base (complete)
10. Phase 9: hybrid BM25 + dense + RRF retrieval (complete)
11. Phase 10: cross-encoder reranking and local grounded generation (current)
12. Phase 11 and later: formal RAG evaluation, model serving, frontend, production observability, CI/CD, and AWS delivery

Each later capability will be introduced as a separate scoped phase.

## Security / Secrets Guidance

- Commit only `.env.example`, never `.env`.
- Do not put passwords, API keys, cloud credentials, or tokens in source code or images.
- Use environment variables locally and a managed secret store for future deployments.
- Treat values in `.env.example` as non-production placeholders.
- Keep the unauthenticated local MLflow UI bound to `127.0.0.1`; never expose it publicly.
- Keep the local llama.cpp endpoint bound to loopback; verify the GGUF checksum before startup.
- Treat retrieved text as untrusted evidence and never execute generated remediation actions automatically.
- Load joblib/cloudpickle model artifacts only from trusted locally generated sources.

## Future Deployment Strategy

The planned portfolio deployment path is GitHub Actions to AWS IAM OIDC,
Amazon ECR, an EC2 host, and Docker Compose. Phase 10 contains no AWS resources,
deployment workflows, credentials, or production infrastructure.
