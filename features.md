# AegisAI Feature and Bug Journal

Statuses: `PLANNED`, `IN PROGRESS`, `DONE`, `BLOCKED`, `DEFERRED`.

## Phase 9 — Hybrid retrieval

| ID | Status | Feature | Verification target |
|---|---|---|---|
| F-009-001 | DONE | Audited corpus service metadata and reproducible active-snapshot fingerprint | All 15 sources reviewed; five corrected documents re-ingested; 20 chunks replaced and fingerprint recorded |
| F-009-002 | DONE | Deterministic BM25 and exact pgvector dense retrieval with shared filters | Unit and real PostgreSQL integration tests pass |
| F-009-003 | DONE | Fixed equal-weight RRF hybrid retrieval and offline search CLI | Exact rank/score/tie tests, filtered cases, and real CLI search pass |
| F-009-004 | DONE | Versioned 50-query benchmark, manually curated qrels, frozen split, metrics, and latency reports | Development inputs frozen; one untouched final evaluation completed |
| F-009-005 | DONE | Phase 9 documentation, CI, and regression validation | Retrieval CI job, Ruff, regressions, YAML, Compose config, and Git hygiene pass |

## Phase 9 bugs and failed attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-009-001 | FIXED | The first editable-install attempt could not reach pinned build dependencies through the managed sandbox. | Re-ran the unchanged per-package install with approved network access; `rank-bm25` 0.2.2 and both local RAG packages installed. |
| B-009-002 | FIXED | A two-document BM25 unit fixture gave all matching terms non-positive corpus IDF, so zero-score nonmatches legitimately sorted first. | Expanded the synthetic fixture to represent a minimally meaningful corpus; production BM25 parameters and behavior were not changed. |
| B-009-003 | FIXED | The first development freeze manifest included measured BM25 build time and host environment, which would make the final preflight equality check nondeterministic. | Kept only hashes, counts, and retrieval contracts in the freeze; moved timing/environment facts to per-run reports and regenerated development output before the single final run. |

## Phase 9 measured verification

- Corpus audit: 15/15 documents reviewed; service vocabulary extended with six
  authoritative OpenTelemetry Demo identities; only five matching runbooks
  changed. Real ingestion updated five documents and replaced 20 of 65 chunks.
- Snapshot: 15 active documents, 65 chunks, fingerprint
  `f5a7d43a5ca429013ef4117b52a36ca68e4e4b4f4e1d16a6d13e89867f59443b`.
- Benchmark: `retrieval-v1-d0069399f493`; 50 primary queries, 100 manually
  curated qrels, 30/20 frozen split, and zero primary queries with filters.
- Development NDCG@10: BM25 0.711, dense 0.751, hybrid 0.815.
- One-time final NDCG@10: BM25 0.670, dense 0.732, hybrid 0.733. Final hybrid
  Recall@5/MRR@10/Hit@10 were 0.750/0.785/1.000.
- Secondary filters: six cases, 1.000 hit rate. Real hybrid CLI search ranked
  database-connection corrective actions first for connection-pool pressure.
- Phase 9 retrieval: 21 tests passed against PostgreSQL/pgvector; Phase 8
  ingestion 24; Phase 7 lifecycle 26; Phase 6 classifier 21; Phase 5 anomaly
  23; Phase 4 features 29; Phase 1 lab 17; telemetry/ML/RAG services 17/1/1;
  Java 37; Kafka integration 2. All passed. Ruff was clean across every Python
  scope; all six existing images built; full Compose health passed and all
  validation containers/network were removed while named volumes were retained.


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

## Phase 5 features

### F-005-001 — Reproducible anomaly capture campaign

- **Scope:** Define and orchestrate the minimum independent normal/fault capture set without duplicating Phase 1 capture logic.
- **Initial approach:** Declarative interleaved plan, per-run validation, explicit cooldown/recovery, and generated accepted/rejected run record.
- **Implementation:** `anomaly-v1.json` and the resumable campaign command reuse `run_capture`, checkpoint accepted/rejected attempts, verify recovery, and restart email after memory-leak runs.
- **Verification:** Plan structure/count/recovery tests pass; the completed real campaign accepted 16 validated runs and recorded one rejected pre-capture startup attempt.
- **Status:** Implemented and validated.

### F-005-002 — Dataset readiness, labels, eligibility, and run split

- **Scope:** Enforce scenario/run/window gates, authoritative service localization labels, explicit service exclusions, and zero-overlap deterministic splitting.
- **Initial approach:** Validate Phase 4 lineage against raw manifests and `scenarios.json`; train on normal runs only.
- **Implementation:** Readiness checks counts, eligible normal windows, raw files, duration consistency, restored flags, and scenario mappings; seed-42 split validation proves exact coverage and no overlap.
- **Verification:** The legacy two-run dataset fails with all expected deficits; focused unit tests pass.
- **Status:** Implemented.

### F-005-003 — Leakage-safe metric and model feature matrix

- **Scope:** Join catalog-owned service features with compact robust metric-deviation features.
- **Initial approach:** Fit metric baselines and median imputation only on normal training rows; exclude unsafe Sum values and all metadata/targets.
- **Implementation:** Phase 4 catalog columns combine with eight robust metric-deviation summaries; service/global median/MAD baselines and median imputation retain explicit fit/transform boundaries.
- **Verification:** Tests cover normal-only fitting, missing baselines, Sum exclusion, immutable transform state, imputation, and metadata leakage.
- **Status:** Implemented.

### F-005-004 — Robust and Isolation Forest detectors

- **Scope:** Implement a transparent robust top-k detector and a deterministic Isolation Forest with common score direction.
- **Initial approach:** Compare only on validation and calibrate thresholds from normal validation scores.
- **Implementation:** Both larger-is-more-anomalous detectors share the fitted matrix; validation comparison uses the predeclared rule and normal-only 95th-percentile thresholds.
- **Verification:** Direction, zero-scale, deterministic forest, and threshold tests pass.
- **Status:** Implemented.

### F-005-005 — Evaluation and reproducible artifacts

- **Scope:** Service, run, scenario, service, and localization metrics plus a reload-verified trusted local artifact bundle.
- **Initial approach:** Deterministic model identity and machine-readable sidecars under ignored artifact storage.
- **Implementation:** Service/run/scenario/service/localization reports and a coherent joblib bundle are written with deterministic identity, schema, split, threshold, predictions, and training report sidecars.
- **Verification:** The synthetic 16-run integration fixture trains, saves, reloads, reproduces exact scores, and reopens predictions without Docker.
- **Status:** Implemented and validated against the real Phase 5 dataset; reload reproduced exact scores.

## Phase 5 bugs and failed attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-005-001 | FIXED | The first anomaly-package install could not reach PyPI from the managed sandbox. | Re-ran the unchanged pinned install with approved network access. |
| B-005-002 | FIXED | Pytest could not enumerate the user-profile temporary directory in the managed filesystem. | Used a repository-local ignored `--basetemp`; all 22 initial tests passed. |
| B-005-003 | FIXED | The first real normal campaign attempt was rejected when OpenTelemetry Demo Checkout was transiently unhealthy during initial startup. | The campaign recorded the full failure, accepted the other 15 planned runs, and a resumable pass captured only the missing sixth normal run. |
| B-005-004 | FIXED | The first service regression batch ran pytest from the repository root, so service-local `app` packages were not importable. | Re-ran each unchanged suite from its owning service directory; telemetry 17/17, ML 1/1, and RAG 1/1 passed. |
| B-005-005 | FIXED | Docker Desktop became unavailable after the capture campaign, temporarily blocking Java/Testcontainers, Kafka integration, and Docker image validation. | After the daemon was restarted, the lab was cleanly removed, Java passed 37/37, Kafka passed 2/2, and all six Compose images built. |

## Phase 5 measured verification

- Campaign: 16 accepted 60-second runs (6 normal; 2 for each fault scenario), 1 rejected pre-capture startup attempt, deterministic recovery and email restart applied.
- Feature dataset: `phase4-v1-d0a2e0c1e709`, 561 service windows, 9,806 metric windows, 159 eligible normal windows; readiness PASS.
- Split: 4 normal training runs, 1 normal plus 5 fault validation runs, 1 normal plus 5 fault test runs; zero overlap.
- Model: 46 features; 107/138/150 train/validation/test rows; Isolation Forest selected; model `anomaly-v1-4c84405c580f`; exact reload verification passed.
- Untouched test: service ROC-AUC 0.651, PR-AUC 0.444, precision 0.455, recall 0.417, F1 0.435, normal FPR 0.231; Hit@1 0.20, Hit@3 0.60, MRR 0.46.
- The model detected all five test fault runs but also the sole normal run. Memory-leak injected-service recall was zero; results are explicitly non-production.
- Phase 5: 22 unit and 1 integration tests passed; Phase 4: 29 passed; Phase 1 tooling: 16 passed; telemetry/ML/RAG services: 17/1/1 passed; Ruff clean.
- Java/Spring/Testcontainers: 37 passed; Kafka integration: 2 passed; all six existing Compose images built; no Phase 5 container was added; all validation containers/networks were removed.

## Phase 6 features

### F-006-001 — Resumable classification capture campaign

- **Scope:** Reuse ten validated Phase 5 fault runs and capture four additional compatible runs per class without duplicating capture logic.
- **Initial approach:** Extend the declarative campaign format with validated existing-run seeds, then use the existing resume, restoration, cooldown, health, and memory-recovery paths.
- **Implementation:** `classification-v1.json` seeds ten validated Phase 5 fault runs and the extended campaign checkpoint preserves `existing` versus `campaign` provenance while revalidating every accepted run.
- **Verification:** The resumed real campaign completed PASS with 30 accepted runs (six per class), twenty new captures, two recorded rejected attempts, flag recovery, cooldown, and memory-service restart.
- **Status:** DONE.

### F-006-002 — Frozen anomaly scoring and run aggregation

- **Scope:** Load and verify the immutable Phase 5 artifact, score eligible service/windows, and produce one compact service-independent top-three row per fault run.
- **Initial approach:** One artifact adapter plus a versioned 30-feature catalog and deterministic aggregation.
- **Implementation:** `FrozenAnomalyAdapter` is the only joblib load path; it verifies model/schema/threshold sidecars and applies persisted Phase 5 transforms. Deterministic aggregation emits one 30-feature row from the top-three eligible windows without service columns.
- **Verification:** Model `anomaly-v1-4c84405c580f` scored 776 real rows with finite scores and 219 threshold decisions; no Phase 5 fit method was called. Ranking/aggregation/leakage tests pass.
- **Status:** DONE.

### F-006-003 — Classification dataset, readiness, and frozen split

- **Scope:** Persist one Parquet row per run with lineage/quality sidecars, enforce six runs per class, and freeze two new test runs per class before development.
- **Initial approach:** Deterministic dataset identity and seed-42 run hashing with explicit leakage checks.
- **Implementation:** Versioned catalog, Parquet/manifest/quality/split sidecars, raw-manifest readiness, and deterministic preference for two new test runs per class.
- **Verification:** Dataset `classification-v1-1090d5095a33` passed at 30 unique rows, 30 features, six runs per class, 20 development and 10 test IDs with zero overlap.
- **Status:** DONE.

### F-006-004 — Cross-validated classifier comparison

- **Scope:** Compare Logistic Regression and Random Forest using fold-local preprocessing, macro-F1 selection, and development-only diagnostics.
- **Initial approach:** Fixed sklearn pipelines with four-fold stratified CV and a predeclared tie-break.
- **Implementation:** Four-fold stratified CV clones complete sklearn pipelines per fold. Logistic Regression includes median imputation/scaling; Random Forest includes median imputation and the fixed small-data configuration.
- **Verification:** Logistic macro F1 was 0.100; Random Forest was 0.303 and won by the frozen rule. The single untouched test produced 0.300 accuracy and 0.270 macro F1; no post-test retuning occurred.
- **Status:** DONE.

### F-006-005 — Reproducible classifier artifact and offline CLI

- **Scope:** Build/readiness/train/evaluate/score commands, deterministic artifact sidecars, explainability diagnostics, and exact reload verification.
- **Initial approach:** Trusted joblib pipeline plus manifest, split, metrics, CV, predictions, and report files.
- **Implementation:** Build/anomaly-score/readiness/train/evaluate/score commands and deterministic bundle/JSON/Parquet sidecars include full lineage, class/feature ordering, split, metrics, diagnostics, and performance.
- **Verification:** `classifier-v1-d37b9861572f` saved as a 66,012-byte bundle; a fresh load reproduced exact predictions and probabilities. Phase 6 package tests and Ruff pass.
- **Status:** DONE.

## Phase 6 bugs and failed attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-006-001 | FIXED | The first Phase 6 Ruff pass found three import-order/unused-import issues and four long lines in the initial package slice. | Applied mechanical import removal/reordering and line wrapping; no behavior or model methodology changed. |
| B-006-002 | FIXED | The first real campaign had one Docker-startup health rejection, one telemetry-validation rejection, and the long-running command was later terminated by the execution environment with 7 new runs checkpointed. | No gate was weakened: rejected/uncheckpointed attempts remained excluded, the campaign resumed from its validated checkpoint, and it completed PASS with 30 accepted runs. |

## Phase 6 measured verification

- Campaign: 30 accepted 60-second fault runs, six per class; 20 new accepted runs; 2 recorded rejected attempts; 1 interrupted uncheckpointed raw attempt excluded; recovery complete.
- Phase 4 dataset: `phase4-v1-45ebffa2ddf3`, 1,091 service windows, 18,116 metric windows, quality PASS, 33.521-second build.
- Frozen anomaly scoring: 776 eligible rows, 219 strict threshold decisions, no failures or refitting.
- Classification dataset: `classification-v1-1090d5095a33`, 30 rows, 30 features, balanced classes, 20/10 frozen split with zero overlap.
- CV: Logistic macro F1 0.100; Random Forest macro F1 0.303; Random Forest selected without test data.
- Untouched test: accuracy/balanced accuracy 0.300, macro F1 0.270, top-2 accuracy 0.600, ROC-AUC OVR macro 0.625, log loss 1.510. CPU/high-latency recall was zero.
- Artifact: `classifier-v1-d37b9861572f`, 66,012 bytes, exact reload verification passed.
- Automated verification: Phase 6 classifier 20 unit + 1 integration tests; Phase 5 anomaly 22 unit + 1 integration; Phase 4 features 29; telemetry lab 17; telemetry/ML/RAG services 17/1/1; Java 37; Kafka integration 2. All passed, and Ruff was clean across every Python scope.
- Docker verification: all six project images built; the complete Compose stack reached healthy/running state (with `kafka-init` exiting 0); all four public health endpoints returned the expected service name and `UP`; validation containers and the network were removed while named volumes were preserved.

## Phase 7 features

### F-007-001 — Isolated local MLflow environment

- **Scope:** Version-pinned lifecycle package, repo-local SQLite tracking, filesystem artifacts, environment overrides, optional loopback-only UI, and secret-safe logging.
- **Approach:** Keep MLflow out of services and core Phase 5/6 packages; make initialization idempotent and test it against temporary stores.
- **Verification:** Repo-local initialization produced SQLite experiment IDs 1 and 2; the optional `127.0.0.1:5000` UI returned HTTP 200 and was stopped cleanly. Configuration, blank override, directory, and secret-key tests pass.
- **Status:** DONE.

### F-007-002 — Truthful frozen-artifact imports

- **Scope:** Validate and hash the canonical Phase 5/6 artifacts, preserve lineage/metrics/limitations, log complete inference models, and register only real persisted models.
- **Approach:** Dedicated anomaly/classifier importers use normal trusted loaders, explicit signatures, compact lineage artifacts, and idempotent registry lookup.
- **Verification:** Real imports registered anomaly/classifier versions 1 from their normal trusted loaders, preserved the exact frozen metrics, and recorded canonical joblib hashes `35a5cb...9704` and `a9b24d...07b7`; repeated imports returned `REUSED` with no new version.
- **Status:** DONE.

### F-007-003 — Alias promotion, rollback, verification, and audit

- **Scope:** Candidate/champion lifecycle with deterministic validation gates, dependency enforcement, alias resolution, JSONL history, and fixture-tested rollback.
- **Approach:** Keep MLflow aliases authoritative while recording every transition locally; do not fabricate duplicate real versions.
- **Verification:** Both candidate and champion aliases resolve to their single truthful v1; version/alias smoke inference passes, audit events were appended, missing/mismatched upstream and invalid promotions fail, and two-version fixture rollback reassigns champion without deletion.
- **Status:** DONE.

### F-007-004 — Lifecycle CLI, documentation, and CI

- **Scope:** Init/import/promote/rollback/verify/audit/resolve commands, optional JSON output, model-lifecycle documentation, CI integration, and full regression validation.
- **Approach:** Stable error codes and noninteractive commands over reusable lifecycle modules.
- **Verification:** The dedicated package has 14 non-integration and 12 SQLite integration tests after final test classification, Ruff is clean, the real CLI/UI paths pass, and CI retains every earlier job while adding isolated lifecycle validation.
- **Status:** DONE.

## Phase 7 bugs and failed attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-007-001 | FIXED | The initial MLflow 3.17 classifier log used the sklearn flavor's default skops serialization, which rejected trusted Random Forest internals (`sklearn.tree._tree.Tree` and `numpy.dtype`). The run failed before any classifier registry version was created. | Selected MLflow's explicit cloudpickle serialization for this trusted canonical pipeline, retained the original joblib as an auxiliary artifact, and hardened the CLI boundary to normalize unexpected third-party failures without routine stack traces. |
| B-007-002 | FIXED | The first Java/Testcontainers regression reached 37 tests but reported eight infrastructure errors because the Docker Desktop daemon was stopped; no Java assertion failed. | Verified the missing Docker named pipe, started the installed Docker Desktop daemon, retained the required PostgreSQL-backed tests, and reran the unchanged Maven suite. |
| B-007-003 | FIXED | Hosted workflow validation rejected the Phase 7 `model-lifecycle` job before scheduling because job-level `env` evaluated `${{ runner.temp }}` before the runner context was available. | Removed both early expressions and added a runtime Bash setup step that derives `AEGIS_MLFLOW_RUNTIME_ROOT`, `MLFLOW_TRACKING_URI`, and `MLFLOW_ARTIFACT_ROOT` from `$RUNNER_TEMP`, writes them to `$GITHUB_ENV`, and creates the temporary artifact directory without changing lifecycle tests. |
| B-007-004 | FIXED | After runtime-safe CI isolation was added, hosted CI injected MLflow path overrides into every lifecycle test; `test_default_paths_are_repo_local` inherited those values and compared an intentional runner-temporary path with the repository-local default. | Isolated the default-path test by deleting every path-related environment variable read by lifecycle configuration, added explicit database/artifact/audit/default-URI assertions, strengthened the separate override test, and reran all 26 lifecycle tests successfully. |

## Phase 7 measured verification

- MLflow 3.17.0; SQLite `sqlite:///C:/projects/AegisAI/.runtime/mlflow/mlflow.db`; filesystem artifact root `.runtime/mlflow/artifacts`; no container or always-on server added.
- Experiments: anomaly `1`, classifier `2`; successful run IDs `dfe364018fa24c6ca3691141faed91c9` and `5e13ba2c69bf4ab98c22327db5a4931e`.
- Registry: `AegisAI-AnomalyDetector` v1 and `AegisAI-IncidentClassifier` v1; both `candidate` and `champion` aliases resolve to v1; champion model URIs verified.
- Imports: anomaly 3.580 seconds; classifier 3.287 seconds; repeated imports reused versions. Champion lookup was 0.037–0.038 seconds and full verification approximately 2.380 seconds per model.
- Storage: SQLite 1,036,288 bytes; MLflow artifacts 1,698,581 bytes; logged anomaly/classifier models 531,178 / 422,529 bytes. The store retains the truthful failed pre-registration classifier run from B-007-001.
- Full regressions: Phase 7 lifecycle 26 tests; Phase 6 classifier 21; Phase 5 anomaly 23; Phase 4 features 29; Phase 1 lab 17; telemetry/ML/RAG 17/1/1; Java 37; Kafka integration 2. All passed; Ruff clean; all six images built; full Compose health passed and validation containers/network were removed.

## Phase 8 — RAG ingestion and vector knowledge base

### F-008-001 — Curated operational knowledge corpus

- **Status:** DONE
- Add a controlled, reviewable Markdown corpus with explicit document type, service, incident type, version, and synthetic-source metadata.

### F-008-002 — Deterministic heading-aware ingestion

- **Status:** DONE
- Add normalized parsing, stable document/checksum/chunk identities, model-tokenizer chunking, quality reports, and reproducible run manifests.

### F-008-003 — Isolated embedding provider boundary

- **Status:** DONE
- Add normalized 384-dimensional local BGE embeddings for real runs and a deterministic injected fake provider for fast offline tests and CI.

### F-008-004 — PostgreSQL pgvector knowledge schema

- **Status:** DONE
- Add Python-owned Alembic migrations, atomic idempotent persistence, inactive-source handling, status/validation commands, and exact vector smoke validation.

## Phase 8 bugs and failed attempts

| ID | Status | Finding | Resolution |
|---|---|---|---|
| B-008-001 | FIXED | The first package-version query could not reach the package index from the restricted sandbox. | Repeated the read-only version query with approved network access, then selected explicit compatible dependency pins without changing the environment. |
| B-008-002 | FIXED | The shell-default Python was 3.13, so the package correctly rejected installation outside its required Python 3.12 range. | Kept the Phase 8 runtime constraint and installed and validated through the existing Python 3.12 `aegis` Conda environment. |
| B-008-003 | FIXED | The first sandboxed pytest run could not access pytest's user-profile temporary directory; nine fixture setups errored while nine tests passed. | Directed pytest's base temporary directory to the repository's ignored `.runtime` tree and retained the tests unchanged. |
| B-008-004 | FIXED | The first real-model command ran inside the restricted network sandbox and Hugging Face could not check one optional normalization config, even though the pinned model was cached and ingestion completed. | Repeated validation with approved model-network access, kept the cache under ignored `.runtime/rag`, and pinned the resolved model commit in configuration and manifests. |
| B-008-005 | FIXED | The first quality report counted five identical synthetic-postmortem disclaimer chunks and treated only newly embedded chunks as the corpus chunk total. | Made each synthetic disclaimer scenario-specific and separated full-corpus chunk statistics from per-run embedded-chunk statistics. |
| B-008-006 | FIXED | The first unchanged telemetry regression inherited the same inaccessible user-profile pytest temporary root seen during Phase 8 tests; 15 tests passed and two fixture setups errored. | Re-ran the unchanged suite with its base temporary directory under ignored `.runtime`; all 17 tests passed. |
| B-008-007 | FIXED | Sandboxed Maven first resolved its home to `C:\.m2`; redirecting it into `.runtime` then required a wrapper download blocked by sandbox networking. | Re-ran the unchanged wrapper with approved access to the existing user Maven cache and Docker; all 37 Java tests passed. |
| B-008-008 | FIXED | The first dependency-version reporting probe assumed the `pgvector` package exported `__version__`, so it stopped after printing two versions. | Used standard package metadata for every dependency and captured the complete installed version set without changing code or packages. |
| B-008-009 | FIXED | Final requirements review found the draft run manifest lacked completion/schema/timing fields and the draft quality report lacked p95, empty-chunk, and dimension-mismatch metrics. | Extended both persisted and file manifests, added measured pipeline timings and schema versions, completed the quality contract and serious-error gate, and covered the fields in PostgreSQL integration tests. |

## Phase 8 measured verification

- Corpus: 15 documents (5 runbooks, 5 postmortems, 3 troubleshooting guides, 1 architecture note, 1 procedure); 13 explicitly synthetic documents; all five target incident types plus `general` represented.
- Real embedding model: `BAAI/bge-small-en-v1.5` at revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; local CPU; 384 dimensions; normalized vectors; 65 stored chunks; 2,354 model tokens; 15–64 tokens per heading-aware chunk (p50 37, p95 51.6); zero empty/duplicate chunk bodies, dimension mismatches, or non-finite embeddings.
- Fresh real ingestion: parse/chunk 0.038282 seconds; embedding 0.849749 seconds (76.493 chunks/second); database work 0.719566 seconds; overall ingestion 1.611222 seconds, excluding model construction performed before the pipeline timer.
- Idempotency: final repeat run discovered 15, skipped/unchanged 15, inserted/updated/deactivated 0, and wrote 0 chunks in 0.105155 seconds. Exact smoke query for database connection exhaustion ranked that synthetic postmortem's root-cause chunk first.
- Storage: PostgreSQL 18.6; pgvector 0.8.6; Alembic revision `0001_rag_vector_schema`; 15 active documents, 0 inactive documents, 65 `vector(384)` chunks. The existing incident row survived the same-major image change.
- Phase 8 tests: 24/24 passed against the isolated `aegis_rag_test` database, including hidden/runtime/raw/binary discovery exclusions; Ruff passed. CI YAML parsed, Compose configuration resolved, and no invalid `${{ runner.temp }}` expressions remain.
- Full regressions: Java 37; telemetry service 17; ML/RAG health services 1/1; Phase 1 lab 17; Phase 4 features 29; Phase 5 anomaly 23; Phase 6 classifier 21; Phase 7 lifecycle 26; Kafka integration 2. All passed; combined Ruff clean; all six service/worker images built; full Compose health passed and validation containers/network were removed without deleting named volumes.
