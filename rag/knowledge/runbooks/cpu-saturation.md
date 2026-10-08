---
title: CPU Saturation Response
document_type: runbook
version: 1
services: [platform, telemetry-service, ad]
incident_types: [cpu_saturation]
synthetic: true
---
# CPU Saturation Response

## Detection

Confirm sustained CPU utilization above the service baseline for at least ten minutes. Compare host, container, and process metrics so throttling is not mistaken for application demand. Check request rate, latency, error rate, and recent deployments over the same window.

## Triage

Identify the hottest instances and threads. Separate user traffic from background work, retries, garbage collection, and telemetry export. Capture a bounded profile when it is safe. Do not restart every replica before preserving evidence.

## Mitigation

Roll back a correlated deployment, reduce optional batch work, or add bounded capacity. Apply rate limiting only with the incident commander’s approval. Validate that latency and queue depth recover, not just CPU utilization.

## Escalation and recovery

Escalate to the owning service team when saturation persists after traffic and release checks. Record graphs, profile references, changes, and timestamps. Remove temporary capacity only after a stable observation period.
