# Incident Management API

Phase 3 provides a manual incident-management API at
`http://localhost:8080/api/v1/incidents`. It does not consume Kafka events,
run anomaly detection, authenticate users, or implement hard deletion.

## Start the service

Start only PostgreSQL and the incident service:

```powershell
docker compose up -d --build --wait postgres incident-service
```

Flyway applies pending migrations during application startup. Hibernate validates
the mapped entities against that schema and does not create or alter tables.

## Create and retrieve an incident

```powershell
$created = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/api/v1/incidents `
  -ContentType application/json `
  -Body @'
{
  "title": "Checkout latency above SLO",
  "description": "p95 latency exceeded 2 seconds",
  "severity": "HIGH",
  "owner": "payments",
  "affected_services": ["checkout-service", "payment-service"]
}
'@

Invoke-RestMethod "http://localhost:8080/api/v1/incidents/$($created.id)"
```

New incidents start in `OPEN`. Service names are trimmed, lowercased, and
deduplicated before persistence.

Example response (timestamps, UUID, and version vary):

```json
{
  "id": "f2a337b4-b066-4d6d-905c-9356d63e6f0c",
  "title": "Checkout latency above SLO",
  "description": "p95 latency exceeded 2 seconds",
  "severity": "HIGH",
  "status": "OPEN",
  "owner": "payments",
  "affected_services": ["checkout-service", "payment-service"],
  "root_cause": null,
  "remediation": null,
  "created_at": "2026-10-06T06:30:00Z",
  "updated_at": "2026-10-06T06:30:00Z",
  "resolved_at": null,
  "closed_at": null,
  "version": 1
}
```

## List and filter incidents

The list endpoint is paginated, defaults to `page=0&size=20`, caps `size` at
100, and orders by newest creation time first. Optional filters are `status`,
`severity`, `service`, and `owner`.

```powershell
Invoke-RestMethod `
  "http://localhost:8080/api/v1/incidents?status=OPEN&severity=HIGH&service=checkout-service&page=0&size=20"
```

The response owns a stable page envelope with `content`, `page`, `size`,
`total_elements`, and `total_pages`.

## Update incident details

`PATCH /api/v1/incidents/{id}` accepts only `title`, `description`, `severity`,
`owner`, `affected_services`, `root_cause`, and `remediation`. Unknown fields,
including `status`, timestamps, and `version`, are rejected. Omitted fields are
unchanged. An empty string clears an optional text field; an empty
`affected_services` array clears that collection.

```powershell
Invoke-RestMethod `
  -Method Patch `
  -Uri "http://localhost:8080/api/v1/incidents/$($created.id)" `
  -ContentType application/json `
  -Body @'
{
  "severity": "CRITICAL",
  "owner": "incident-command",
  "root_cause": "Connection pool exhaustion",
  "remediation": "Increase the pool and reduce upstream timeout"
}
'@
```

## Transition incident status

Use the dedicated transition endpoint; status is not writable through the
generic patch operation.

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/v1/incidents/$($created.id)/transition" `
  -ContentType application/json `
  -Body '{"target_status":"INVESTIGATING","note":"Incident commander assigned","actor":"on-call"}'
```

Allowed transitions:

| Current | Allowed targets |
|---|---|
| `OPEN` | `INVESTIGATING`, `RESOLVED` |
| `INVESTIGATING` | `MITIGATED`, `RESOLVED` |
| `MITIGATED` | `INVESTIGATING`, `RESOLVED` |
| `RESOLVED` | `INVESTIGATING`, `CLOSED` |
| `CLOSED` | none |

Entering `RESOLVED` sets `resolved_at`. Reopening to `INVESTIGATING` clears
`resolved_at`, while the historical transition remains in the timeline.
Entering `CLOSED` sets `closed_at`; closed incidents cannot transition again.

## Timeline notes and history

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/v1/incidents/$($created.id)/timeline" `
  -ContentType application/json `
  -Body '{"message":"Database team engaged","actor":"on-call"}'

Invoke-RestMethod `
  "http://localhost:8080/api/v1/incidents/$($created.id)/timeline?page=0&size=100"
```

Timeline entries are returned oldest first, with UUID as the stable tie-breaker.
The service creates entries for incident creation, detail updates, root-cause
updates, remediation updates, status changes, and manual notes.

## Concurrency and errors

The incident entity uses JPA optimistic locking. Concurrent writes based on a
stale persisted version cannot overwrite newer data; conflicts return HTTP 409.
The numeric `version` response field is an opaque concurrency value and should
not be interpreted as a mutation count.

Errors use `application/problem+json` fields including `type`, `title`,
`status`, `detail`, `instance`, `error_code`, and `timestamp`. Validation
responses also include `field_errors`. Important mappings are:

| Condition | Status | `error_code` |
|---|---:|---|
| Invalid body or parameter | 400 | `validation_failed` |
| Unknown incident | 404 | `incident_not_found` |
| Invalid lifecycle transition | 409 | `invalid_incident_transition` |
| Concurrent stale update | 409 | `optimistic_lock_conflict` |
| Relational constraint conflict | 409 | `database_conflict` |

## Persistence and reset behavior

Normal shutdown keeps the `aegis-postgres-data` named volume:

```powershell
docker compose down
docker compose up -d --wait postgres incident-service
Invoke-RestMethod "http://localhost:8080/api/v1/incidents/$($created.id)"
```

Only use the following when intentionally deleting all local Compose data,
including Kafka and PostgreSQL volumes:

```powershell
docker compose down -v
```
