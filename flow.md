# AegisAI Runtime Flow Journal

This journal tracks implemented request, data, and failure paths. Future phases must read it before extending cross-service behavior.

## Phase 3

### Before implementation

1. `GET /api/v1/health` reaches the incident-service health controller and returns a static service status.
2. The incident service starts with an in-memory H2 database; Flyway is disabled and no incident tables or repositories exist.
3. Phase 2 telemetry events flow independently through Kafka. The incident service is not a Kafka producer or consumer.

### Current modification

Phase 3 replaces the incident service's H2-only health shell with PostgreSQL
runtime persistence, Flyway schema ownership, and controller/service/repository
paths for manual incident management. Phase 2 Kafka code remains unchanged and
is deliberately not connected to the incident service.

### After implementation

#### Incident creation

```text
POST /api/v1/incidents
  -> IncidentController.create(CreateIncidentRequest)
  -> Jakarta Bean Validation
  -> IncidentService.create() @Transactional
  -> IncidentEntity.create()
  -> IncidentRepository.save()
  -> TimelineEntryRepository.saveAndFlush(INCIDENT_CREATED)
  -> PostgreSQL transaction commit
  -> IncidentMapper.toResponse()
  -> 201 Created + Location
```

Failure path: request validation returns a structured `400`; either database write failing rolls back both writes. The initial status is `OPEN`, and an `INCIDENT_CREATED` timeline entry is persisted before commit.

#### Incident query

```text
GET /api/v1/incidents/{id}
  -> IncidentController.get()
  -> IncidentService.get() @Transactional(readOnly=true)
  -> IncidentRepository.findById()
  -> IncidentMapper.toResponse()
  -> 200 OK

GET /api/v1/incidents?filters&page&size
  -> IncidentController.list()
  -> parameter validation (size <= 100)
  -> IncidentService.list() @Transactional(readOnly=true)
  -> IncidentSpecifications.withFilters()
  -> IncidentRepository.findAll(specification, pageable)
  -> IncidentMapper.toSummary()
  -> PageResponse
  -> 200 OK
```

Failure path: an unknown incident identifier returns a structured `404`. List queries compose optional status, severity, affected-service, and owner specifications, then return a bounded page ordered by creation time descending.

#### Incident mutation

```text
PATCH /api/v1/incidents/{id}
  -> IncidentController.update(UpdateIncidentRequest)
  -> IncidentService.update() @Transactional
  -> IncidentRepository.findById()
  -> IncidentEntity.updateDetails()
  -> TimelineEntryRepository.saveAll() when meaningful fields change
  -> IncidentRepository.flush() / @Version check
  -> PostgreSQL transaction commit
  -> IncidentMapper.toResponse()
  -> 200 OK

POST /api/v1/incidents/{id}/transition
  -> IncidentController.transition(TransitionIncidentRequest)
  -> IncidentService.transition() @Transactional
  -> IncidentRepository.findById()
  -> IncidentEntity.transitionTo() validates IncidentStatus.canTransitionTo()
  -> timestamp mutation
  -> TimelineEntryRepository.save(STATUS_CHANGED)
  -> IncidentRepository.flush() / @Version check
  -> PostgreSQL transaction commit
  -> IncidentMapper.toResponse()
  -> 200 OK
```

Failure paths: an invalid lifecycle transition returns `409`; an optimistic-lock conflict returns `409`; validation failures return `400`; no partial timeline or incident update is committed. Status can change only through the transition path.

#### Timeline

```text
POST /api/v1/incidents/{id}/timeline
  -> IncidentController.addTimelineNote(AddTimelineNoteRequest)
  -> IncidentService.addTimelineNote() @Transactional
  -> IncidentRepository.existsById()
  -> TimelineEntryRepository.save(NOTE_ADDED)
  -> 201 Created

GET /api/v1/incidents/{id}/timeline
  -> IncidentController.getTimeline()
  -> IncidentService.getTimeline() @Transactional(readOnly=true)
  -> TimelineEntryRepository.findByIncidentId()
     ordered by createdAt ASC, id ASC
  -> IncidentMapper.toTimelineResponse()
  -> PageResponse
  -> 200 OK
```

Failure path: timeline access for an unknown incident returns `404`.

#### Exception paths

```text
invalid request DTO/parameter
  -> ApiExceptionHandler
  -> 400 ProblemDetail(validation_failed + field_errors when available)

missing incident
  -> IncidentNotFoundException
  -> ApiExceptionHandler
  -> 404 ProblemDetail(incident_not_found)

invalid IncidentEntity.transitionTo()
  -> InvalidIncidentTransitionException
  -> transaction rollback
  -> ApiExceptionHandler
  -> 409 ProblemDetail(invalid_incident_transition)

stale @Version during flush
  -> OptimisticLockingFailureException
  -> transaction rollback
  -> ApiExceptionHandler
  -> 409 ProblemDetail(optimistic_lock_conflict)
```

#### Application startup and persistence

`Compose -> PostgreSQL health check -> incident service -> Flyway validation/migration -> Hibernate schema validation -> ready health`

Failure path: the incident service does not start if PostgreSQL is unavailable,
a migration fails, or the ORM mapping does not match the migrated schema.
`docker compose down` removes containers and the network but preserves
`aegis-postgres-data`; `docker compose down -v` is the explicit destructive reset.

### Explicitly unchanged in Phase 3

- Kafka telemetry remains isolated from incident creation.
- No automated anomaly-to-incident flow exists.
- No authentication, Redis, ML, RAG, frontend, or cloud flow is introduced.

## Phase 4 — Offline feature engineering

### Before implementation

Phase 1 produced validated manifests and OTLP JSONL files. No reusable parser,
event-time window aggregation, model-ready schema, Parquet output, or dataset
validator existed. The production `ml-service` remained a health-only shell.

### Current modification

Add an independently installable `ml/feature_engineering` package. It reads raw
captures without modifying them and owns OTLP normalization, deterministic
aggregation, schema/catalog contracts, quality gates, Parquet I/O, and CLI use.
The long-running Compose topology and production services remain unchanged.

### After implementation

```text
python -m aegis_features.cli build --run <run-id> ...
  -> cli.main() / cli.run()
  -> dataset.build_dataset()
  -> loaders.load_manifest()
  -> manifest/run/scenario/label/signal validation
  -> loaders.iter_signal_records()
  -> dataset.SourceDeduplicator.accept()
  -> otlp.parse_export_request()
  -> otlp.normalize_record() / normalize_metrics|logs|traces()
  -> typed observations.py records
  -> aggregation.build_service_windows() / build_metric_windows()
  -> windows.window_start_ns() event-time assignment
  -> quality.validate_observations() / validate_feature_rows()
  -> dataset._write_parquet() with explicit PyArrow schemas
  -> manifest.json + quality.json
  -> dataset.validate_dataset() reopens and verifies both Parquet files
```

Failure paths reject missing/failed manifests, unknown
scenarios, conflicting labels or duplicate IDs, excessive invalid timestamps,
non-finite features, schema mismatches, and inconsistent manifest row counts.
Negative span durations are counted and excluded from duration statistics. CLI
errors are caught as `FeatureEngineeringError` or safe
configuration `ValueError` and exit without exposing an internal stack trace.

```text
python -m aegis_features.cli inspect --run <run-id>
  -> inspection.inspect_run()
  -> load_manifest() / iter_signal_records()
  -> normalize_record()
  -> compact signal/service/metric/severity/kind inventory JSON

python -m aegis_features.cli validate --dataset <dataset-id>
  -> dataset.validate_dataset()
  -> reopen manifest.json + quality.json + both Parquet tables
  -> compare exact catalog order and Arrow types/nullability
  -> recompute deterministic IDs and quality invariants
  -> dataset.dataset_summary()

python -m aegis_features.cli summary --dataset <dataset-id>
  -> dataset.dataset_summary()
  -> compact runs/scenarios/services/rows/time-range/class/features/status JSON
```

### Explicitly unchanged in Phase 4

- The production `ml-service` remains health-only.
- Kafka does not create features or incidents automatically.
- No model training, fitted preprocessing, inference, MLflow, RAG, Redis,
  authentication, frontend, or AWS path was added.

## Phase 5 — Offline anomaly detection

### Current modification

Phase 5 adds a reproducible capture campaign plus an independently installable
offline anomaly package. It consumes Phase 4 Parquet datasets and never changes
the production `ml-service` API or the running service topology.

### Dataset and training path

```text
anomaly-v1 campaign plan
  -> existing telemetry-lab run_capture()
  -> per-run Phase 1 validation
  -> flag restoration / health check / cooldown / memory-service restart
  -> generated campaign record with accepted and rejected run IDs
  -> Phase 4 feature build over accepted campaign runs
  -> Phase 5 readiness gate
  -> deterministic run-level train / validation / test split
  -> normal-training-only metric baselines and median imputer
  -> RobustZScoreDetector and IsolationForest comparison on validation
  -> normal-validation quantile threshold
  -> one untouched test evaluation
  -> ignored model bundle, manifest, metrics, split, schema, and predictions
```

Failure paths reject malformed campaign plans, failed/restoration-invalid
captures, insufficient scenario counts, insufficient eligible normal windows,
run overlap, fault rows in training, metadata leakage, non-finite matrices, and
untrusted or inconsistent artifact inputs.

### Offline scoring path

```text
python -m aegis_anomaly.cli score --model <model-id> --dataset <dataset-id>
  -> load trusted local joblib bundle
  -> validate Phase 4 dataset identity and schema
  -> apply persisted metric baseline (transform only)
  -> apply persisted median imputer and feature order
  -> detector.score_samples()
  -> persisted threshold decision and compact JSON summary
```

### Explicitly unchanged in Phase 5

- No HTTP prediction endpoint or production `ml-service` dependency is added.
- No Kafka inference, incident creation, classifier, MLflow, RAG, Redis,
  frontend, observability pipeline, or AWS flow is added.

### Validated Phase 5 instance

The real campaign produced dataset `phase4-v1-d0a2e0c1e709` and passed the
6-normal/2-per-fault/150-normal-window gate with 159 eligible normal windows.
The deterministic split fitted 107 normal rows, selected Isolation Forest from
138 validation rows, and evaluated once on 150 test rows. The trusted local
bundle `anomaly-v1-4c84405c580f` reloads to bit-identical scores. Its weak
service localization and false positive on the only normal test run remain
reported limitations; no test-driven retuning was performed.
