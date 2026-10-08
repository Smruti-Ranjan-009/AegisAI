---
title: Synthetic Postmortem — Batch Work Caused API CPU Saturation
document_type: postmortem
version: 1
services: [incident-service, platform]
incident_types: [cpu_saturation, high_latency]
synthetic: true
---
# Synthetic Postmortem: Batch Work Caused API CPU Saturation

This fictional exercise models an API and co-located batch workload; it is not a production record.

## Impact

For 24 minutes, incident API tail latency exceeded its objective and a small fraction of requests timed out. Stored data remained correct.

## Timeline

At 10:02 a maintenance job began on every replica. At 10:07 CPU throttling and request queues rose. The alert fired at 10:10. Responders paused the job at 10:18 and latency recovered by 10:26.

## Root cause

The job schedule lacked per-replica jitter and shared the request worker pool. A recent data-volume increase pushed simultaneous work past available CPU.

## Corrective actions

Move maintenance work to a bounded worker pool, add schedule jitter, alert on throttling and queue time, and load-test the job at projected data volume.
