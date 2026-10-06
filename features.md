# AegisAI Feature and Bug Journal

Statuses: `PLANNED`, `IN PROGRESS`, `DONE`, `BLOCKED`, `DEFERRED`.

## Phase 3 Features

| ID | Status | Feature | Verification target |
|---|---|---|---|
| F-003-001 | DONE | PostgreSQL Compose service, persistent volume, health check, and environment-driven incident-service connection | Compose healthy; application and database restart persistence passed |
| F-003-002 | DONE | Flyway-managed incident, affected-service, timeline, constraint, and index schema | Six migrations and Hibernate validation passed on PostgreSQL 18.4 |
| F-003-003 | DONE | Create, retrieve, list, filter, and patch incidents | MockMvc/Testcontainers and Compose E2E passed |
| F-003-004 | DONE | Enforced lifecycle transitions with resolution and closure timestamps | 25-case matrix and full Compose lifecycle passed |
| F-003-005 | DONE | Immutable chronological incident timeline with manual notes | Nine-entry Compose timeline verified in deterministic order |
| F-003-006 | DONE | Transactional atomicity and optimistic locking | Deliberate second-write rollback and stale-version tests passed |
| F-003-007 | DONE | Structured RFC 9457-style API errors | 400, 404, lifecycle 409, and optimistic-lock 409 tests passed |
| F-003-008 | DONE | Phase 3 documentation, CI, and reproducible validation | Full regression/build/Compose validation passed; clean shutdown preserved volumes |

## Phase 3 Bugs and Failed Attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-003-001 | FIXED | The first Maven Wrapper compile attempt failed because this execution environment resolved its cache to the unwritable path `C:\\.m2`. | Scope Wrapper artifacts to an ignored workspace path and use the approved normal Maven cache for validation; compilation/tests passed. |
| B-003-002 | FIXED | The first Testcontainers run executed 36 tests; 27 domain tests passed, while 8 integration/context tests errored before application startup because Docker rejected the client's API version 1.32 (minimum 1.40). | Pin Testcontainers 1.21.4; final PostgreSQL suite passed 37/37. |
| B-003-003 | FIXED | After Docker compatibility was restored, 35 of 36 tests passed because an API test incorrectly assumed a newly created aggregate must expose version 0. Hibernate legitimately increments the owning version when persisting its affected-services collection. | Keep nullable `Long` internally for correct new-entity detection, and assert the numeric/opaque version contract; stale-version regression passed. |
| B-003-004 | FIXED | Specification review after the first green Java run found three naming mismatches: `incident_timeline`, `CREATED`, and transition field `status` differed from the required `incident_timeline_entries`, `INCIDENT_CREATED`, and `target_status` contracts. | Preserve V1-V4; V5/V6 and contract updates passed clean-schema and Compose E2E validation. |
| B-003-005 | FIXED | Phase 0/2 Python regression commands could not import pytest or Ruff from the active base Conda interpreter; telemetry-lab's standard-library suite still passed 14/14. | Use the existing documented `aegis` Conda environment, which contains the service-pinned test tools; ML/RAG tests and all Ruff checks then passed. |
| B-003-006 | FIXED | Telemetry rerun reached 15 passing tests, but two `tmp_path` fixtures errored because sandboxing denied pytest's user-temp directory. | Repository-scoped `--basetemp` rerun passed 17/17; no source/test behavior changed. |
| B-003-007 | FIXED | First full Compose startup health-gated the incident service because PostgreSQL 18.4 rejected the legacy `/var/lib/postgresql/data` volume mount. | Use `/var/lib/postgresql`; full Compose, health, persistence, and restart validation passed. |
| B-003-008 | FIXED | The added null affected-service regression received the expected 400, but its JSONPath treated the bracketed field-error map key as an array expression. | Assert non-empty `field_errors`; final Java suite passed 37/37. |

## Feature histories

### F-003-001 — PostgreSQL runtime

- **Scope/acceptance:** Pinned PostgreSQL container, health-gated incident startup, environment configuration, and persistent named volume.
- **Initial approach:** Replace the Phase 0 H2 default with one PostgreSQL connection contract shared by direct runtime and Compose.
- **Implementation:** `docker-compose.yml`, `.env.example`, and `application.yml` now use PostgreSQL 18.4, `pg_isready`, `depends_on: service_healthy`, and `aegis-postgres-data`.
- **Verification:** Testcontainers and Compose connect to PostgreSQL 18.4; application, incident-service restart, and database restart persistence checks pass.
- **Related decisions:** D-003-001, D-003-002.

### F-003-002 — Flyway schema

- **Scope/acceptance:** Reproducible incident, affected-service, and timeline tables with useful constraints and query-driven indexes; Hibernate validates only.
- **Initial approach:** Four migrations for the three tables and indexes.
- **Implementation:** V1-V4 created the schema; after those migrations ran, V5/V6 corrected public naming without mutating successful history. Six migrations now reconstruct the final schema.
- **Verification:** A real PostgreSQL test confirms six successful Flyway records and Hibernate mapping validation; the same migrations pass during Compose startup.
- **Related decisions:** D-003-002, D-003-003, D-003-011.

### F-003-003 — Incident create/read/list/update

- **Scope/acceptance:** Thin `/api/v1/incidents` controllers, dedicated DTOs, normalized affected services, bounded pagination, composable filters, and controlled patch fields.
- **Initial approach:** Manual mapping plus `JpaSpecificationExecutor`; no mapping/query libraries.
- **Implementation:** `IncidentController`, `IncidentService`, `IncidentMapper`, repositories/specifications, DTO records, and the incident entity implement the request path. Unknown JSON fields are rejected so protected fields cannot be silently ignored.
- **Verification:** MockMvc/Testcontainers and Compose E2E cover create, get, patch, list, and combined status/severity/service/owner filtering.
- **Related decisions:** D-003-003, D-003-005.

### F-003-004 — Lifecycle

- **Scope/acceptance:** Explicit transition matrix, UTC timestamp rules, terminal closure, and no generic status setter.
- **Initial approach:** Put the invariant on `IncidentEntity` and inject a UTC `Clock` into the service.
- **Implementation:** `IncidentStatus.canTransitionTo()` and `IncidentEntity.transitionTo()` enforce all allowed edges, resolution/reopen semantics, and closure time.
- **Verification:** A 25-case transition matrix, timestamp tests, valid/invalid MockMvc transitions, and the full Compose lifecycle pass.
- **Related decisions:** D-003-004, D-003-010.

### F-003-005 — Timeline

- **Scope/acceptance:** Stable event enum, automatic audit entries, manual notes, and deterministic paginated retrieval.
- **Initial approach:** Independent timeline entity keyed by incident UUID to avoid a bidirectional graph.
- **Implementation:** Creation, details, root cause, remediation, status, and manual-note events persist in `incident_timeline_entries`; reads sort by creation time and UUID.
- **Verification:** API integration and Compose E2E verify automatic and manual entries in chronological order; the final incident produces nine entries.
- **Related decisions:** D-003-003, D-003-008.

### F-003-006 — Atomicity and concurrency

- **Scope/acceptance:** No partial incident/timeline state and no silent stale overwrite.
- **Initial approach:** Service-layer Spring transactions plus aggregate `@Version`.
- **Implementation:** Mutating service methods define transaction boundaries and flush within them so database/locking errors surface before response mapping.
- **Verification:** A real PostgreSQL test deliberately violates the second timeline insert and proves the incident rolled back; a detached stale entity raises an optimistic-locking failure.
- **Related decisions:** D-003-007, D-003-008.

### F-003-007 — Structured errors

- **Scope/acceptance:** Safe 400/404/409 Problem Details with stable machine codes and field-level validation messages.
- **Initial approach:** One small `@RestControllerAdvice`; no custom framework.
- **Implementation:** `ApiExceptionHandler` maps validation, malformed input, not found, lifecycle, optimistic-lock, and relational conflicts without returning SQL or exception types.
- **Verification:** MockMvc covers validation, unknown ID, protected/unknown patch fields, lifecycle conflict, and the focused optimistic-lock HTTP 409 mapping; persistence also proves the stale-write conflict.
- **Related decisions:** D-003-009.

### F-003-008 — Documentation, CI, and validation

- **Scope/acceptance:** Incident/database guides, current architecture, permanent journals, Testcontainers-enabled CI, regressions, Docker E2E, persistence restart, and clean shutdown.
- **Initial approach:** Preserve every Phase 0–2 workflow and extend only the incident job and default Compose stack.
- **Implementation:** README, architecture, incident API, database, three journals, Compose, and CI are updated. No Phase 4 dependency or integration was added.
- **Verification:** Java passes 37/37; all Python and Ruff regressions, telemetry-lab, live Kafka integration, Docker build/start/E2E/restarts, and Git hygiene checks pass.
- **Related decisions:** D-003-001 through D-003-012.

## Detailed bug and failed-attempt histories

### B-003-001 — Maven cache path denied

- **Discovery/reproduction:** The first `mvnw.cmd ... compile` failed immediately with `AccessDeniedException: C:\\.m2` in the restricted execution environment.
- **Root cause:** The sandbox's effective home path is read-only and Maven Wrapper derived its cache there.
- **Attempts:** Verified no global Maven executable was installed. Added the repository-local `.m2/` path to `.gitignore` and scoped Wrapper distribution storage locally during the retry.
- **Final fix:** Validation uses an approved Maven execution context; no application behavior changed. Normal developer terminals continue to use the standard Maven user cache.
- **Regression:** Java compilation and the full suite subsequently ran successfully.

### B-003-002 — Docker Engine/Testcontainers API incompatibility

- **Discovery/reproduction:** First full test run: 36 tests discovered, 27 domain tests passed, and eight context/integration tests errored before startup with Docker API 1.32 rejected by Docker Engine 29.8.1.
- **Root cause:** Spring Boot 3.4.6 managed Testcontainers 1.20.6/docker-java 3.4.1, whose default negotiation was incompatible with the current engine.
- **Rejected workaround:** Host-only API environment configuration and skipping container tests would make CI/developer behavior diverge or hide required persistence coverage.
- **Final fix:** Pin the compatible Testcontainers 1.x maintenance release 1.21.4.
- **Regression:** PostgreSQL container startup, Flyway, context, API, rollback, and locking tests all execute successfully.

### B-003-003 — Incorrect initial-version assumption

- **Discovery/reproduction:** The second full run passed 35/36; the remaining assertion expected version 0 but read version 1.
- **Root cause:** Hibernate versions the complete aggregate and increments the owner when its affected-services collection is initially persisted.
- **Attempt that did not solve it:** Changing primitive `long` to nullable `Long` correctly improved Spring Data new-entity detection but intentionally did not exclude collection changes from optimistic locking.
- **Final fix:** Keep aggregate-safe locking and test the public numeric/opaque version contract instead of a provider-specific starting value.
- **Regression:** Full suite passed, including the stale-version test.

### B-003-004 — Public naming mismatches

- **Discovery/reproduction:** A specification-to-implementation audit after the first green run compared the exact table, event, and request examples.
- **Root cause:** Early implementation used shorter internal terms rather than the explicit public contract names.
- **Rejected fix:** Rewriting V3/V4 after they had successfully executed would violate the migration immutability rule.
- **Final fix:** Add V5/V6 migrations and update JPA, enum, DTO, tests, errors, and documentation to the final names.
- **Regression:** Clean-database Testcontainers migration and Compose HTTP requests using `target_status` passed.

### B-003-005 — Missing Python validation dependencies

- **Discovery/reproduction:** Direct `python -m pytest` and `python -m ruff` commands in all three Python services returned `No module named`; the same interpreter ran the dependency-free telemetry-lab suite successfully.
- **Root cause:** The active base Conda interpreter did not have the independently pinned service requirements installed.
- **Rejected workaround:** Reporting the tests as failed or installing one shared root requirement set would misrepresent the environment and violate service isolation.
- **Attempt revised:** Before generating new virtual environments, inspection found the existing documented `aegis` Conda environment already contained pytest, Ruff, and the service dependencies.
- **Final fix:** Run each service independently from its own directory through `conda run -n aegis`, preserving the per-service requirement files without duplicating an already provisioned environment.
- **Regression:** ML and RAG passed 1/1 each; all three Ruff checks passed. Telemetry's remaining environment issue is tracked separately as B-003-006.

### B-003-006 — Pytest user-temp permission denied

- **Discovery/reproduction:** Telemetry ran 17 tests; 15 passed and two replay tests errored during `tmp_path` setup with access denied under the user's global temporary directory.
- **Root cause:** The managed filesystem permits writes in the repository but not that external pytest temp directory.
- **First fix attempt:** Point `--basetemp` at `.tmp/pytest`; pytest cannot create a missing parent directory, so the same two fixtures errored with `FileNotFoundError` while 15 tests passed.
- **Final fix:** Create the ignored `.tmp` parent, then point `--basetemp` at its `pytest` child.
- **Regression:** Telemetry passed 17/17 using the repository-scoped base temp.

### B-003-007 — PostgreSQL 18 volume layout

- **Discovery/reproduction:** The first `docker compose up -d --wait` started Kafka and the Python APIs, but PostgreSQL exited 1 and the incident dependency remained unstarted.
- **Root cause:** PostgreSQL 18 changed the official image layout to major-version-specific data directories; mounting the legacy child path is rejected to keep upgrades within one mount boundary.
- **Rejected fixes:** Downgrading from the requested pinned 18.4 image or adding a startup sleep would not address the data-layout contract.
- **Final fix:** Mount `aegis-postgres-data` at `/var/lib/postgresql` while retaining `pg_isready` and health-conditioned incident startup.
- **Regression:** PostgreSQL became healthy, the incident service waited correctly, and data survived both service and database restarts.

### B-003-008 — Bracketed validation path assertion

- **Discovery/reproduction:** Final Java rerun failed 1/37 at only the JSONPath assertion for a null element; HTTP status was already 400.
- **Root cause:** The Bean Validation field name contains `[0]`, which JSONPath interpreted as traversal rather than a literal map key.
- **Final fix:** Assert the stable public guarantee—a populated `field_errors` object—without coupling to provider-specific nested path formatting.
- **Regression:** Final Java/PostgreSQL suite passed 37/37.

## Phase 3 final verification

- Java/Spring/Testcontainers: 37 passed, 0 failed, 0 errors, 0 skipped.
- Telemetry service: 17 passed; Ruff clean.
- ML service: 1 passed; Ruff clean.
- RAG service: 1 passed; Ruff clean.
- Phase 1 telemetry lab: 14 passed.
- Phase 2 Kafka integration: 2 passed against the live Compose broker/worker.
- Docker: all six project images built; PostgreSQL and Kafka healthy; topic initializer exited 0; every service started.
- API: create/read/list/filter/update/note, full lifecycle, validation/not-found/conflict errors, and nine ordered timeline entries passed.
- Persistence: incident remained after incident-service restart, PostgreSQL restart, and final incident image recreation.
- Shutdown: `docker compose down --remove-orphans` removed all containers/network while preserving `aegis-postgres-data` and `aegis-kafka-data`.

## Phase 4 Features

| ID | Status | Feature | Verification target |
|---|---|---|---|
| F-004-001 | DONE | Installable offline feature-engineering package and CLI | Editable install and all four commands passed |
| F-004-002 | DONE | Official-protobuf OTLP normalization for metrics, logs, and traces | Signal fixtures, AnyValue, service, and timestamp tests passed |
| F-004-003 | DONE | Deterministic event-time windows, run isolation, and deduplication | Boundary, multi-run, duplicate, and determinism tests passed |
| F-004-004 | DONE | Wide service-window log/trace/volume features | Feature aggregation and empty-signal tests passed |
| F-004-005 | DONE | Long metric-window features for all OTLP metric types | Gauge, Sum, Histogram, ExponentialHistogram, Summary tests passed |
| F-004-006 | DONE | Parquet, catalog, manifest, quality report, and independent validation | End-to-end round trip and corruption gates passed |
| F-004-007 | DONE | Real-data inventory, documentation, CI, and Phase 0–3 regression | Two-run dataset and full regression/build/Compose validation passed |

## Phase 4 working history

### F-004-001 — Offline package and CLI

- **Scope:** Add a Python 3.12 `src`-layout package under `ml/feature_engineering`; do not modify service dependencies or add a container.
- **Initial approach:** Standard `pyproject.toml`, explicit console/module CLI, and package-local tests/fixtures.
- **Implementation:** Added the Python 3.12 `src` package, module/console CLI, pinned package-owned dependencies, and inspect/build/validate/summary commands.
- **Verification:** Editable install succeeded; CLI commands passed on fixtures and both real runs.

### F-004-002 — OTLP normalization

- **Scope:** Validate OTLP JSON through official protobuf requests and normalize resource-scoped observations with central AnyValue conversion.
- **Initial approach:** `opentelemetry-proto` 1.45.0 plus protobuf JSON parsing, preserving event timestamps and `__unknown__` service observations.
- **Implementation:** Official request messages validate JSON; central AnyValue/resource helpers create typed metric, log, and span observations.
- **Verification:** Fixtures cover every AnyValue shape, service fallback, event timestamps, five metric types, severities, status, kinds, and negative duration.

### F-004-003 — Deterministic windows and input safety

- **Scope:** UTC `[start, end)` windows, SHA-256 IDs, run isolation, label validation, and source-record deduplication.
- **Initial approach:** Integer nanosecond floor division and canonical JSON hashes before observation expansion.
- **Implementation:** Integer-nanosecond UTC windows and SHA-256 logical IDs group by run/service; record-level canonical hashing handles duplicates.
- **Verification:** Exact boundaries, UTC, service/run separation, deterministic IDs/builds, identical duplicate, and conflicting duplicate tests pass.

### F-004-004 — Service-window features

- **Scope:** Stable log, trace, signal-volume, and metric-volume features without target leakage.
- **Initial approach:** Typed observation accumulators with one shared deterministic percentile implementation.
- **Implementation:** Stable catalog-driven log, trace, metric-volume, and total-volume features use structural-zero and nullable-statistic semantics.
- **Verification:** Aggregation, safe rates, percentiles, error/kind semantics, and empty-signal tests pass; real sanity ranges pass.

### F-004-005 — Metric-window features

- **Scope:** Long-form, unit/type-safe metric aggregates with conservative histogram semantics.
- **Initial approach:** Numeric Gauge/Sum statistics; semantically available Histogram/ExponentialHistogram/Summary aggregates; no counter rate.
- **Implementation:** Metric windows group by name/unit/type and retain series cardinality; Gauge/Sum numeric and conservative aggregate statistics are type-aware.
- **Verification:** All five metric types are covered; unit/type isolation passes; real captures contain 189 Sum, 54 Gauge, and 22 Histogram identities.

### F-004-006 — Dataset contracts and quality

- **Scope:** Explicit schemas, catalog APIs, Parquet output, manifest/quality lineage, and validator that reopens files.
- **Initial approach:** PyArrow schemas and JSON sidecars with strict finite/range/identity/count checks.
- **Implementation:** Explicit Arrow schemas, Zstandard Parquet, deterministic dataset IDs, JSON lineage/quality sidecars, and an independent reopen validator are complete.
- **Verification:** Fixture builds match logically across repetitions; row-count corruption is rejected; the real dataset validates with 67/944 rows.

### F-004-007 — Real validation and regressions

- **Scope:** Inventory and build the existing normal plus CPU-saturation captures, update docs/CI, and preserve Phase 0–3 behavior.
- **Initial approach:** Reuse captures read-only; generated Parquet remains ignored.
- **Implementation:** Inventory/contracts/docs/README/architecture/CI are updated; generated outputs are ignored; no service or container dependency was added.
- **Verification:** Two validated 30-second runs (473 records, 4,857,399 bytes) built dataset `phase4-v1-74f868854916` in 1.327649 seconds. Phase 0–3 regressions, six Docker image builds, full Compose health, and clean shutdown passed.

## Phase 4 Bugs and Failed Attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-004-001 | FIXED | The first editable-install attempt could not reach PyPI because the managed sandbox denied network access while creating the isolated build environment. | Re-ran the same pinned install with approved network access; PyArrow, protobuf, OpenTelemetry proto, and the editable package installed successfully. |
| B-004-002 | FIXED | The first Ruff pass reported 12 import-style, unused-import, and line-length violations after the initial package implementation. | Applied mechanical import/format corrections; package and test lint now pass. |
| B-004-003 | FIXED | The default Java regression attempt again resolved Maven Wrapper storage to the sandbox-denied `C:\.m2` path. | Reused the Phase 3 approved Maven/Docker execution context; all 37 tests passed without source changes. |
| B-004-004 | FIXED | The default Docker build could not read the user Buildx instance directory under the managed filesystem. | Re-ran the unchanged Compose build with approved Docker access; all six project images built. |

### B-004-001 — Sandboxed dependency installation

- **Discovery/reproduction:** `conda run -n aegis python -m pip install -e "ml\feature_engineering[test]"` exhausted retries because socket access to PyPI was denied.
- **Root cause:** Dependency download was outside the default managed sandbox, not a package-resolution or version conflict.
- **Attempted fixes:** The original command was allowed to fail and recorded; dependency pins were not loosened.
- **Final fix:** Execute the same scoped installation with approved network access.
- **Regression:** The package imports, all feature tests execute, and PyArrow writes/reads the real dataset.

### B-004-002 — Initial lint findings

- **Discovery/reproduction:** Ruff found one unused import, collection ABC imports from `typing`, one import-order issue, and long lines.
- **Root cause:** Initial implementation prioritized an executable vertical slice before its first lint pass.
- **Final fix:** Use `collections.abc`, remove the unused import, sort imports, and wrap long expressions without changing behavior.
- **Regression:** `python -m ruff check ml\feature_engineering` reports all checks passed.

### B-004-003 — Maven cache permission recurrence

- **Discovery/reproduction:** The Phase 0–3 Java regression stopped before Maven startup with `AccessDeniedException: C:\.m2`.
- **Root cause:** The same managed-environment home/cache resolution documented in B-003-001; no Java or Phase 4 behavior caused it.
- **Final fix:** Run the unchanged wrapper command in the already approved Maven/Testcontainers context.
- **Regression:** Java/PostgreSQL suite passed 37/37.

### B-004-004 — Docker Buildx permission boundary

- **Discovery/reproduction:** Compose configuration parsed, but the first image build could not access `C:\Users\smrut\.docker\buildx\instances`.
- **Root cause:** Docker Desktop user configuration lies outside the writable workspace sandbox.
- **Final fix:** Re-run the unchanged build with scoped approved Docker access.
- **Regression:** All six project images built; the complete stack became healthy and later shut down cleanly.

## Phase 4 final verification

- Feature engineering: 29 tests passed; Ruff clean.
- Real data: 473 records / 9,291 observations / 4,857,399 bytes produced 67 service windows and 944 metric windows; validation PASS.
- Java/Spring/Testcontainers: 37 passed, 0 failures/errors/skips.
- Telemetry service: 17 passed; ML service: 1 passed; RAG service: 1 passed; all Ruff checks clean.
- Phase 1 telemetry lab: 14 passed; Phase 2 live Kafka integration: 2 passed.
- Docker: Compose config valid; all six project images built; PostgreSQL, Kafka, worker, incident, telemetry, ML, and RAG health/startup passed.
- Shutdown: all containers/network removed; PostgreSQL and Kafka named volumes preserved.
