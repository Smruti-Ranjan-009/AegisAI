---
title: Deployment Correlation Troubleshooting
document_type: troubleshooting
version: 1
services: [platform, incident-service, ml-service, rag-service, telemetry-service]
incident_types: [service_failure, high_latency, cpu_saturation, memory_leak]
synthetic: true
---
# Deployment Correlation Troubleshooting

## Establish correlation

Compare the first abnormal signal with rollout start, replica replacement, configuration activation, and traffic shift. Segment metrics by old and new version. A nearby deployment is evidence to test, not proof of causation.

## Choose a safe experiment

Pause rollout progression before capacity falls further. If old replicas remain healthy, shift a bounded amount of traffic between versions or roll back through the normal release mechanism. Avoid manual mutation that cannot be reproduced.

## Interpret results

Recovery on the old version strengthens the deployment hypothesis. No recovery should redirect investigation to dependencies, traffic shape, and shared infrastructure. Preserve version identifiers and all experiment times.

## Follow through

After stability, reproduce the failure under controlled conditions and add a release test that observes the actual failure signal.
