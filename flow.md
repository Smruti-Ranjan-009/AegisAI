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
