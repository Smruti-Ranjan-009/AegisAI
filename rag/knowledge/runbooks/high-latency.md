---
title: High Latency Response
document_type: runbook
version: 1
services: [platform, incident-service, telemetry-service, frontend, image-provider]
incident_types: [high_latency]
synthetic: true
---
# High Latency Response

## Establish the symptom

Compare median and tail latency with the service objective and normal traffic shape. Segment by route, status, instance, region, and caller. Confirm whether the delay is server processing, queueing, or dependency time.

## Investigate

Review saturation, thread or worker pools, database query time, connection waits, garbage collection, and retry volume. Correlate the first change with deployments and configuration events. Prefer traces that represent affected requests.

## Mitigate

Roll back a correlated release, reduce optional work, or restore a failed dependency. Add capacity only when the bottleneck can use it. Protect the system from retry storms with bounded backoff and admission controls.

## Validate

Watch tail latency, errors, throughput, and queue depth through a sustained recovery window. Record which signal confirmed recovery and which temporary mitigations must be removed.
