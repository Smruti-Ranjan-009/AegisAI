---
title: Dependency Failure Response
document_type: runbook
version: 1
services: [platform, postgresql, kafka]
incident_types: [dependency_failure]
synthetic: true
---
# Dependency Failure Response

## Confirm the dependency

Use client-side errors and dependency-side health signals to identify the failing boundary. Check name resolution, certificates, connection establishment, pool exhaustion, timeouts, and server capacity. A single client failure is not proof of a shared outage.

## Contain retries

Verify timeout, backoff, and circuit-breaker behavior. Reduce nonessential traffic or pause batch consumers if retries are increasing load. Do not disable safety limits globally.

## Restore service

Fail over only through an established procedure. If configuration changed, compare it with the last known good version and roll back safely. Validate reads and writes before releasing queued work.

## Closeout

Confirm dependent services drain their backlog without another capacity spike. Document the dependency timeline, affected callers, temporary controls, and owners for resilience work.
