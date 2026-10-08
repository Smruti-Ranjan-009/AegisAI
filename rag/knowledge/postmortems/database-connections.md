---
title: Synthetic Postmortem — Database Connection Exhaustion
document_type: postmortem
version: 1
services: [incident-service, postgresql]
incident_types: [dependency_failure, high_latency]
synthetic: true
---
# Synthetic Postmortem: Database Connection Exhaustion

This fictional exercise models exhausted database connections; it is not a production record.

## Impact

Incident writes experienced elevated latency and intermittent failures for 32 minutes. Read-only health endpoints remained available.

## Timeline

Connection wait time rose after a traffic increase at 16:20. Application retries amplified demand. Responders reduced retry concurrency and restarted one leaking client pool; normal service returned at 16:52.

## Root cause

One exception path failed to return connections, while retry settings admitted more concurrent work than the database limit could serve.

## Corrective actions

Test pool release on exceptions, cap total connections by deployment size, alert on acquisition time, and use bounded exponential backoff.
