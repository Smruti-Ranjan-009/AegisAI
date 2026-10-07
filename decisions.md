# AegisAI Engineering Decisions

This journal records implementation decisions as they are made. Future phases must read it before changing established behavior.

## Phase 3 — Incident Management Backend

### D-003-001 — PostgreSQL is the Phase 3 runtime and test database

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** The incident service will use PostgreSQL for local runtime, Docker Compose, and persistence integration tests. Testcontainers will provide an isolated PostgreSQL instance for Maven tests. The Phase 0 H2 runtime dependency and configuration will be removed.
- **Alternatives considered:** Retain H2 for fast tests; use an embedded PostgreSQL emulator.
- **Rationale:** Phase 3 introduces PostgreSQL-specific types, constraints, Flyway migrations, and optimistic locking behavior. Testing against the production database engine avoids dialect drift and false confidence.
- **Consequences:** Incident-service integration tests require a working Docker-compatible container runtime. Pure domain tests remain container-free.

### D-003-002 — Flyway exclusively owns schema evolution

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Flyway versioned SQL migrations create and evolve the incident schema. Hibernate uses `ddl-auto=validate` and never creates or mutates tables.
- **Alternatives considered:** Hibernate schema generation; a single baseline migration containing all Phase 3 tables and indexes.
- **Rationale:** Separating the schema into incidents, affected services, timeline, and indexes makes ordering and future evolution explicit while validating ORM-to-schema compatibility at startup.
- **Consequences:** Applied migrations are immutable. Later schema changes require new migration versions.

### D-003-003 — Keep the incident aggregate small and relationships unidirectional

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Affected services are stored in a normalized collection table mapped as an `@ElementCollection`. Timeline entries are separate entities keyed by a scalar incident UUID rather than a bidirectional object graph.
- **Alternatives considered:** Dedicated affected-service entity; bidirectional incident/timeline JPA association; JSON array storage.
- **Rationale:** The selected mapping preserves normalized relational constraints without adding lifecycle-heavy entities or recursion-prone ORM associations.
- **Consequences:** Timeline queries use a dedicated repository, and application services explicitly coordinate incident and timeline writes in one transaction.

### D-003-004 — Lifecycle transitions are explicit domain behavior

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Incident status has no generic setter. The domain model permits only the documented transition matrix. Entering `RESOLVED` sets `resolved_at`; reopening to `INVESTIGATING` clears it; entering `CLOSED` sets `closed_at`; `CLOSED` is terminal. Every successful mutation updates `updated_at`.
- **Alternatives considered:** Controller-only validation; unrestricted status updates; retaining the first resolution timestamp after reopening.
- **Rationale:** Keeping the invariant on the entity prevents alternate service paths from bypassing lifecycle rules. Clearing `resolved_at` on reopen makes it describe the current resolution rather than historical events, which remain available in the timeline.
- **Consequences:** Historical resolution/reopen activity is represented by timeline entries. Incidents are never hard-deleted in Phase 3.

### D-003-005 — API models are isolated from persistence models

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Controllers expose dedicated request/response DTOs with snake_case JSON. Mapping is explicit and list responses use an application-owned page envelope. Repository filtering uses JPA specifications.
- **Alternatives considered:** Serialize JPA entities directly; adopt a mapping library; expose Spring Data's internal `Page` JSON shape.
- **Rationale:** Manual mapping is small at Phase 3 scale, keeps the wire contract stable, and prevents lazy-loading or persistence internals from leaking through the API.
- **Consequences:** New fields require deliberate mapping changes. Unknown request fields are rejected.

### D-003-006 — Pin Testcontainers 1.21.4 for current Docker compatibility

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Override Spring Boot 3.4.6's managed Testcontainers 1.20.6 version with 1.21.4 while retaining Spring Boot's dependency management for the module set.
- **Alternatives considered:** Set a host-specific Docker API environment variable; skip integration tests when Docker is incompatible; migrate to Testcontainers 2.x.
- **Rationale:** The official 1.21.4 release specifically restores compatibility with recent Docker Engine changes. A dependency-level fix works in local and CI environments without hiding required PostgreSQL tests or depending on developer machine configuration.
- **Consequences:** The override should be removed when a future Spring Boot upgrade manages an equally compatible or newer Testcontainers release.

### D-003-007 — Version the complete incident aggregate

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** The incident's optimistic-lock version covers both scalar columns and the normalized affected-services collection. The API promises a non-negative numeric version, not a particular initial number.
- **Alternatives considered:** Exclude the collection from optimistic locking to force an initial version of zero; expose no version contract.
- **Rationale:** Concurrent affected-service edits must conflict just like concurrent title, severity, or status edits. Hibernate may increment the version while initially persisting the collection, which is a valid provider detail.
- **Consequences:** Clients must treat `version` as an opaque concurrency token and not infer mutation counts from it.

### D-003-008 — Incident mutations and timeline records are atomic

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Create, detail-update, and transition use application-service transaction boundaries that include both the incident aggregate write and its timeline entries. Timeline notes have their own transaction after incident existence is verified.
- **Alternatives considered:** Publish timeline events asynchronously; write timeline records after the incident transaction commits.
- **Rationale:** Phase 3's timeline is the persisted audit history. Committing an incident state without its corresponding history—or history without the state—would violate that contract.
- **Consequences:** A timeline constraint failure rolls back the associated incident mutation. A later event-driven audit stream can be added with an outbox rather than weakening this invariant.

### D-003-009 — Stable HTTP failures use Problem Details

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** API failures use Spring `ProblemDetail` (`application/problem+json`) with stable `error_code`, timestamp, request instance, and field errors when applicable.
- **Alternatives considered:** Custom ad hoc error DTOs; returning framework exception messages.
- **Rationale:** Problem Details provides a standard envelope while explicit codes give clients a stable machine-readable contract and avoid exposing internal exceptions.
- **Consequences:** New failure categories require deliberate error-code and status mappings.

### D-003-010 — Do not hard-delete operational incident records

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Phase 3 exposes no incident delete endpoint. Foreign keys still use cascade cleanup to preserve relational integrity if a future administrative retention process performs controlled deletion.
- **Alternatives considered:** Public hard delete; soft-delete flag in Phase 3.
- **Rationale:** Incidents and timelines are operational audit records. Public deletion is unsafe, while a soft-delete policy would add filtering and retention semantics not yet required.
- **Consequences:** API clients can close incidents but cannot delete them. Retention and administrative deletion remain future policy decisions.

### D-003-011 — Index only implemented Phase 3 query paths

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Index newest-first incident listing, status/severity/owner/service filters, and chronological per-incident timeline reads. Do not add speculative full-text, vector, ML, or analytics indexes.
- **Alternatives considered:** Single-column indexes for every column; broad future-oriented indexing.
- **Rationale:** Composite indexes align with current filter/order patterns and avoid unnecessary write/storage cost.
- **Consequences:** Query plans should be revisited with production-like data and combined-filter evidence in a later performance phase.

### D-003-012 — Mount the PostgreSQL 18 parent data directory

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Mount `aegis-postgres-data` at `/var/lib/postgresql`, not the pre-18 `/var/lib/postgresql/data` path.
- **Alternatives considered:** Downgrade the requested PostgreSQL image; force the legacy `PGDATA` layout.
- **Rationale:** The official PostgreSQL 18 image uses major-version-specific subdirectories and explicitly requires the parent mount for upgrade-safe volume boundaries.
- **Consequences:** The named volume and preservation/reset commands are unchanged, while its internal layout is compatible with PostgreSQL 18.

## Phase 4 decisions

### D-004-001 — Use event time and fixed UTC tumbling windows

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Aggregate each run and service into configurable 60-second UTC `[start, end)` windows using signal event timestamps, never file-read or build time. Window IDs are SHA-256 hashes of schema version, run ID, service, start, and duration.
- **Alternatives considered:** Ingestion-time windows; sliding windows; random IDs.
- **Rationale:** Captures and future at-least-once delivery may be replayed or delayed. Event-time tumbling windows are deterministic, inexpensive, and prevent run/scenario contamination.
- **Consequences:** Missing timestamps are quality failures/drops under a configurable ratio, and late-arrival streaming policy remains future work.

### D-004-002 — Stream normalization and use PyArrow only at the columnar boundary

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Parse JSONL incrementally, aggregate with typed Python records/dictionaries, and use PyArrow 25.0.1 for explicit-schema Parquet I/O.
- **Alternatives considered:** Polars; Pandas plus PyArrow; pure PyArrow compute pipelines.
- **Rationale:** The capture files are naturally record-oriented. Streaming avoids multiple full-dataframe copies on the 16 GB target, while direct PyArrow provides typed, compressed, interoperable output without adding another dataframe dependency.
- **Trade-offs:** Python aggregation is not intended for distributed-scale telemetry; future scale may justify Polars lazy scans or a stream processor while preserving contracts.

### D-004-003 — Decode OTLP JSON with official protobuf definitions

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Use `opentelemetry-proto` 1.45.0 and protobuf JSON parsing for metrics, logs, and traces. Centralize `AnyValue` conversion and resource-attribute handling after protobuf validation.
- **Alternatives considered:** Reuse Phase 2's shallow dictionary validation; implement a complete custom OTLP tree parser.
- **Rationale:** Official messages validate signal structure and enum/type semantics, while one normalization layer prevents scattered fragile dictionary traversal.
- **Consequences:** Proto field-presence semantics define nullability; dependencies belong only to the offline feature package.

### D-004-004 — Keep service features wide and metric features long

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Emit a stable wide `service_windows` table for bounded log/trace/volume features and a long `metric_windows` table keyed by metric name, unit, and type.
- **Alternatives considered:** Pivot every metric into wide columns; average all metric values into service-level statistics.
- **Rationale:** Metric names and units have different meanings and evolving cardinality. Long form prevents unit mixing and unbounded sparse schemas while preserving Phase 5 selection flexibility.
- **Consequences:** Metric-aware modeling will join/filter the second table deliberately; raw high-cardinality attributes do not enter model features.

### D-004-005 — Separate metadata, targets, and predictive features by catalog

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Versioned catalog APIs define ordered metadata, target, and feature columns. `run_id`, `scenario`, `label`, `is_anomaly`, and fault/capture provenance can never be returned as predictive features.
- **Alternatives considered:** Infer features from numeric dtypes; maintain informal documentation only.
- **Rationale:** Type inference would admit boolean targets and future numeric metadata, creating silent target leakage.
- **Consequences:** Schema changes require catalog updates and regression tests; feature schema meaning is immutable within v1.

### D-004-006 — Preserve genuine missing values and reject non-finite values

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Use structural zero for absent event counts/rates, keep undefined statistics nullable, drop timestamp-invalid observations within a configured limit, and reject NaN/infinity before and after Parquet writing. No fitted scaling or imputation occurs.
- **Alternatives considered:** Zero-fill every field; fit imputers/scalers during dataset creation; fabricate timestamps.
- **Rationale:** Zero latency is not equivalent to missing latency, and training-fitted transforms would leak information before Phase 5 splits data by run.
- **Consequences:** Phase 5 owns grouped splitting, fitted preprocessing, and any imputation policy.

### D-004-007 — Deduplicate source records before normalization

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** When a source event ID is present, hash its canonical payload and count identical repeats once; reject the same ID with conflicting content. Phase 1 JSONL lines receive deterministic source identities derived from run, signal, and canonical payload because they do not carry Kafka event IDs.
- **Alternatives considered:** Count all at-least-once records; deduplicate normalized observations independently.
- **Rationale:** Record-level deduplication matches Phase 2 delivery semantics and avoids partially duplicated OTLP batches.
- **Consequences:** Duplicate counts are reported in manifests; genuinely identical Phase 1 export batches within a run are treated as duplicates.

### D-004-008 — Revalidate legacy Phase 1 manifests instead of mutating them

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Reject an explicit non-PASS `validation_status`, but treat legacy schema-v1 manifests without that newer field as eligible only after the Phase 4 loader revalidates their required fields, run identity, scenario/label, signal paths, non-empty records, and protobuf structure.
- **Alternatives considered:** Modify the read-only manifests to add PASS; reject every existing Phase 1 capture because its schema predates the field.
- **Rationale:** Phase 1 recorded PASS as the result of its validator rather than a manifest property. Revalidation preserves immutability and uses the already validated real captures without weakening input checks.
- **Consequences:** Future manifests may carry an explicit status; either format still undergoes structural and OTLP validation.

## Phase 5 decisions

### D-005-001 — Gate final training on independent validated capture runs

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Final Phase 5 training requires at least six normal runs, two runs for each of the five fault scenarios, and 150 eligible normal service windows. The two legacy 30-second captures are not mixed into the consistent 60-second anomaly campaign.
- **Alternatives considered:** Train on the two existing captures; lower the gate; mix 30- and 60-second captures.
- **Rationale:** Independent runs are the unit of generalization, while mixed capture durations would introduce avoidable acquisition confounding.
- **Consequences:** The telemetry lab gains a deterministic campaign orchestrator, and training refuses an insufficient dataset.

### D-005-002 — Separate run faults from injected-service localization labels

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** `run_has_fault` is true for every row in a fault run, while `is_injected_fault_service` is true only for services listed by the authoritative scenario configuration. Non-target services in fault runs are propagation-ambiguous and are excluded from the primary service-level binary evaluation.
- **Alternatives considered:** Label every service in a fault run anomalous; label all non-target services normal.
- **Rationale:** Run-level incident detection and fault-service localization answer different questions, and treating propagated services as known negatives would create incorrect ground truth.
- **Consequences:** Primary service metrics use injected targets versus eligible normal rows; run metrics aggregate with maximum service score.

### D-005-003 — Split by run and fit only on normal training runs

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** A deterministic seed-42 split assigns complete runs to train, validation, or test with zero overlap. Training contains normal runs only; validation and test each receive normal coverage and one run from every fault scenario. Test remains untouched until feature rules, detector choice, and threshold are frozen from validation.
- **Alternatives considered:** Random row splitting; semi-supervised fault fitting; test-driven model selection.
- **Rationale:** Neighboring windows from one capture are correlated, and test feedback must not influence the final detector.
- **Consequences:** Exact run assignments are persisted with the model artifact.

### D-005-004 — Train a global service detector with explicit eligibility

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** The initial global detector excludes `__unknown__`, `flagd`, `load-generator`, `otelcol-contrib`, and `telemetry-docs`. Remaining application services are eligible. Service identity remains metadata rather than a predictive feature. Per-service metric baselines require five normal-training windows and otherwise fall back to a global metric baseline.
- **Alternatives considered:** Include every observed identity; encode service names; fit unstable one-row service baselines.
- **Rationale:** Infrastructure identities have different telemetry-generating roles, and identity encoding could let the model memorize services instead of behavior.
- **Consequences:** Eligibility, exclusions, and baseline coverage are reported in artifacts.

### D-005-005 — Use robust training-only metric deviations and exclude Sum values

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Metric baselines are keyed by service, metric name, unit, type, and statistic and fit only on normal training runs. Gauge mean, histogram/exponential-histogram mean, and summary mean are eligible. Raw Sum values are excluded because Phase 4 does not preserve enough temporality/reset semantics for safe counter rates. Scale is `1.4826 * MAD`, then `IQR / 1.349`, then a finite unit fallback marked uninformative.
- **Alternatives considered:** Wide metric pivots; raw cumulative counter values; validation/test refitting.
- **Rationale:** Robust deviation summaries use metric behavior without mixing semantics or leaking evaluation data.
- **Consequences:** Unknown metrics increment missing-baseline and coverage features but never create new fitted state during transform.

### D-005-006 — Compare two simple detectors and calibrate thresholds on normal validation data

- **Date:** 2026-10-06
- **Status:** Accepted
- **Decision:** Compare a top-k robust z-score detector with a 300-tree Isolation Forest. Both expose larger-is-more-anomalous scores. Select using validation normal FPR proximity to the 5% target, then run detection, localization, supporting AUC, and simplicity. Calibrate each threshold from the 95th percentile of normal validation scores only.
- **Alternatives considered:** Supervised classifiers; deep autoencoders; fault-label threshold tuning.
- **Rationale:** The available campaign is small and synthetic, so transparent unsupervised baselines are more defensible than complex models.
- **Consequences:** No minimum F1 is fabricated, and weak results are reported honestly.

## Phase 6 decisions

### D-006-001 — Preserve a frozen two-stage anomaly/classification architecture

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Phase 6 classifies only fault runs into the five configured incident categories after scoring with the immutable Phase 5 artifact `anomaly-v1-4c84405c580f`. `normal` is not a classifier class. Phase 6 never refits the anomaly metric transformer, imputer, Isolation Forest, feature order, or threshold.
- **Alternatives considered:** A single six-class model; retraining Phase 5 on the expanded campaign; tuning the anomaly gate for classifier performance.
- **Rationale:** Detection and diagnosis are different questions, and changing the upstream detector would invalidate the completed Phase 5 evaluation and lineage.
- **Consequences:** Every classification dataset and artifact records the upstream anomaly model ID and loads it through one trusted local adapter.

### D-006-002 — Retain the discrete Phase 5 threshold exactly as stored

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Use the stored threshold `0.5359423344799236` and strict `score > threshold` decision unchanged. It differs from the reported p95 `0.5341476669796773` because calibration uses `numpy.quantile(..., method="higher")`, selecting an observed order statistic, while the diagnostic p95 uses NumPy's default linear interpolation.
- **Alternatives considered:** Replace the threshold with the interpolated p95; retrain or retune Phase 5.
- **Rationale:** The implementation is internally correct: the discrete threshold and strict comparison give the recorded validation FPR without splitting ties at the cutoff.
- **Consequences:** Documentation distinguishes the selection quantile from the interpolated distribution summary; no Phase 5 defect or mutation is required.

### D-006-003 — Require six independent validated runs per fault class

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Classification readiness requires exactly the five authoritative fault classes and at least six compatible validated 60-second captures per class. A resumable interleaved campaign reuses the two Phase 5 fault runs per class and captures four additional runs per class.
- **Alternatives considered:** Train on the existing ten fault runs; weaken the per-class gate; manufacture balanced samples.
- **Rationale:** One row represents one independent run, so the current two examples per class cannot support a four-fold development comparison plus an untouched test.
- **Consequences:** The minimum dataset has 30 balanced rows; raw captures remain ignored but retained locally.

### D-006-004 — Aggregate one service-independent row per run from top-three anomaly context

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Rank eligible service/windows by frozen Phase 5 anomaly score and aggregate the top three into a compact run vector. Sort by descending score, then window start and service name only as deterministic metadata tie-breakers. Service identity is never encoded or exposed as a predictive column.
- **Alternatives considered:** Classify service windows independently; pivot by service; aggregate every one of the 46 Phase 5 features with many statistics.
- **Rationale:** Run-level rows prevent correlated-window sample inflation, top-three context focuses on abnormal behavior, and service-independent names reduce direct scenario/service leakage.
- **Consequences:** Telemetry can still indirectly identify services, which remains a documented controlled-dataset limitation.

### D-006-005 — Freeze two newly captured test runs per class before model development

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Dataset construction deterministically selects two newly captured Phase 6 runs per class for the final test and persists the split before cross-validation. The remaining four runs per class form development. Seed 42 hashes run IDs for deterministic selection, with a deterministic all-run fallback for fixtures.
- **Alternatives considered:** Random row splitting; using the previously inspected Phase 5 runs as all test cases; selecting the test after CV.
- **Rationale:** The final ten-run test must be isolated from feature/model decisions and should emphasize captures not observed during Phase 5 analysis.
- **Consequences:** Development/test intersections are forbidden, and test IDs cannot enter CV or preprocessing fitting.

### D-006-006 — Compare leakage-safe Logistic Regression and Random Forest pipelines

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Use four-fold shuffled stratified CV with seed 42. Logistic Regression uses fold-local median imputation and standard scaling; Random Forest uses fold-local median imputation without scaling. Compare fixed, modest configurations rather than hyperparameter search.
- **Alternatives considered:** Global preprocessing before CV; boosted trees; deep learning; broad tuning.
- **Rationale:** Twenty development runs require low-variance, inspectable baselines and strict preprocessing isolation.
- **Consequences:** Fold pipelines are independently fitted and the selected complete pipeline is refit on all development rows.

### D-006-007 — Select by macro F1 with a predeclared deterministic tie-break

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Select the highest mean CV macro F1. Differences no greater than 0.01 are treated as practically tied, then balanced accuracy, lower macro-F1 standard deviation, and finally Logistic Regression simplicity decide.
- **Alternatives considered:** Accuracy-only selection; final-test selection; per-class manual preference.
- **Rationale:** All five balanced classes matter equally and the final test must remain untouched until selection and refit are frozen.
- **Consequences:** Weak CV or test performance is reported rather than repaired through test-driven retuning.

### D-006-008 — Persist a complete trusted classifier pipeline with deterministic identity

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** Store the fitted sklearn pipeline, ordered features/classes, upstream anomaly ID, and aggregation contract in one joblib bundle plus JSON/Parquet sidecars. Model identity hashes dataset, upstream model, split, schema, aggregation, classifier configuration, and seed.
- **Alternatives considered:** Save classifier weights alone; duplicate the Phase 5 artifact; use wall-clock model IDs.
- **Rationale:** A coherent versioned bundle prevents preprocessing/order drift while retaining explicit Phase 5 lineage.
- **Consequences:** Joblib loading is restricted to trusted local artifacts and reload must reproduce predictions and probabilities exactly.
