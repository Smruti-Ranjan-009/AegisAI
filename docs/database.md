# Incident Database

The incident service now runs on the Compose PostgreSQL 18.6 pgvector image.
Flyway remains the sole owner of the incident-service tables; Phase 8 Python
Alembic separately owns only the `rag` schema. Hibernate runs with
`ddl-auto=validate` and fails startup if the incident mappings do not match the
migrated schema.

## Relational model

```text
incidents
    |
    +----< incident_affected_services
    |
    +----< incident_timeline_entries
```

### `incidents`

- UUID primary key generated in Java
- required title, severity, status, creation timestamp, update timestamp, and version
- nullable description, owner, root cause, remediation, resolution timestamp, and closure timestamp
- string check constraints for the severity and status enums
- JPA `@Version` column for optimistic locking

Severity values are `CRITICAL`, `HIGH`, `MEDIUM`, and `LOW`. Status values are
`OPEN`, `INVESTIGATING`, `MITIGATED`, `RESOLVED`, and `CLOSED`.

### `incident_affected_services`

- composite primary key: `(incident_id, service_name)`
- foreign key to `incidents(id)`
- one row per normalized affected service
- cascade-on-delete exists for referential cleanup, although Phase 3 exposes no
  incident deletion operation

### `incident_timeline_entries`

- UUID primary key generated in Java
- foreign key to `incidents(id)`
- required event type, message, and UTC creation timestamp
- optional free-text actor; no user or authentication table exists in Phase 3
- stable event values: `INCIDENT_CREATED`, `DETAILS_UPDATED`, `STATUS_CHANGED`,
  `NOTE_ADDED`, `ROOT_CAUSE_UPDATED`, and `REMEDIATION_UPDATED`

Timeline reads use deterministic `created_at ASC, id ASC` ordering.

## Indexes

| Index path | Query served |
|---|---|
| `incidents(created_at DESC)` | default newest-first list |
| `incidents(status, created_at DESC)` | status-filtered list |
| `incidents(severity, created_at DESC)` | severity-filtered list |
| `incidents(owner)` | owner filtering |
| `incident_affected_services(service_name, incident_id)` | affected-service filtering and join |
| `incident_timeline_entries(incident_id, created_at, id)` | chronological timeline lookup |

These indexes correspond to Phase 3 repository queries; no speculative ML,
RAG, vector, or analytics indexes are included.

## Flyway migrations

Migrations live under
`services/incident-service/src/main/resources/db/migration/`:

1. `V1__create_incidents.sql`
2. `V2__create_incident_affected_services.sql`
3. `V3__create_incident_timeline.sql`
4. `V4__create_incident_indexes.sql`
5. `V5__rename_incident_timeline_entries.sql`
6. `V6__standardize_incident_created_event.sql`

V5 and V6 preserve the immutable history of migrations that had already been
executed during development validation while aligning final public terminology.
Do not edit an applied migration. Add a new version for every later schema change.

## Timestamp and transaction conventions

Java uses `Instant` and PostgreSQL uses `TIMESTAMPTZ`. Application time is
provided by a UTC `Clock`. Creation time is immutable; update time changes with
successful mutation. Resolution time describes the current resolved state and
is cleared on reopen. Closure time is set when entering the terminal `CLOSED`
state.

Incident creation, detail mutation, and status transition each write their
timeline records in the same Spring transaction as the incident write. Database
constraint failure rolls back the complete transaction.

## Local persistence

Compose uses the named volume `aegis-postgres-data` mounted at
`/var/lib/postgresql`, the PostgreSQL 18+ parent data path that supports
major-version-specific subdirectories. Normal shutdown preserves it:

```powershell
docker compose down
```

An intentional destructive reset removes it (and other Compose volumes):

```powershell
docker compose down -v
```

The credentials in `.env.example` are local development placeholders, not
production secrets.
