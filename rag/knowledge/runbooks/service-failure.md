---
title: Service Failure Response
document_type: runbook
version: 1
services: [incident-service, ml-service, rag-service, telemetry-service, payment]
incident_types: [service_failure]
synthetic: true
---
# Service Failure Response

## Scope

Determine whether the service is unavailable, degraded, or failing only a subset of requests. Check health probes, error classes, replica readiness, dependency calls, and the most recent deployment or configuration change.

## Stabilization

Route away from unhealthy replicas and pause automated rollout progression. Roll back a strongly correlated release. Preserve logs and deployment metadata before replacing all failed instances.

## Dependency checks

Test required database and event-backbone connectivity from the service network. Distinguish a local startup failure from a shared dependency outage. Avoid retry amplification when a dependency is already saturated.

## Recovery

Restore one healthy path first, validate a representative request, then return traffic gradually. Monitor errors, latency, saturation, and queue depth. Record the trigger, containment, and follow-up owner.
