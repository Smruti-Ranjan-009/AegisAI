---
title: Synthetic Postmortem — Retry Storm Increased Tail Latency
document_type: postmortem
version: 1
services: [ml-service, incident-service, platform]
incident_types: [high_latency, dependency_failure]
synthetic: true
---
# Synthetic Postmortem: Retry Storm Increased Tail Latency

This fictional exercise models synchronized retries during slowdown; it is not a production record.

## Impact

Tail latency across two internal APIs exceeded objectives for 28 minutes. Successful throughput fell even though incoming user traffic was stable.

## Timeline

A downstream service slowed at 11:40. Callers retried immediately and synchronized. Queue depth doubled by 11:46. Responders enabled the existing circuit breaker and lowered retry concurrency; recovery completed at 12:08.

## Root cause

Retry policy lacked jitter and used a timeout longer than the caller’s remaining deadline. Duplicate attempts consumed worker and connection capacity.

## Corrective actions

Propagate deadlines, add exponential backoff with jitter, enforce retry budgets, and test partial dependency slowdown rather than only total failure.
