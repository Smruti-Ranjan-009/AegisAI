---
title: Memory Growth and Leak Response
document_type: runbook
version: 1
services: [platform, incident-service]
incident_types: [memory_leak]
synthetic: true
---
# Memory Growth and Leak Response

## Detection

Confirm that resident memory grows across comparable traffic periods and does not return after normal collection cycles. Review allocation rate, heap usage, container limits, out-of-memory events, and restart frequency.

## Triage

Correlate growth with a release, endpoint, tenant, or background task. Preserve a heap summary or bounded dump according to data-handling policy. Check caches, unbounded collections, connection pools, and retained request payloads.

## Mitigation

Roll back the suspected version or shift traffic to healthy replicas. A controlled rolling restart may restore capacity, but it is containment rather than resolution. Avoid increasing limits without a capacity estimate.

## Verification

Track memory slope through several collection cycles and a representative load window. Close the incident only after growth stops and restart frequency returns to baseline. Attach evidence and a permanent-fix owner.
