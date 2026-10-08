---
title: Cross-Signal Incident Triage Guide
document_type: troubleshooting
version: 1
services: [platform, telemetry-service]
incident_types: [general]
synthetic: true
---
# Cross-Signal Incident Triage Guide

## Start with a timeline

Choose one time window and align deployments, configuration changes, request rate, errors, latency, saturation, logs, and traces. Differences in clock range often create false contradictions.

## Test competing explanations

Write down two or three plausible causes and the signal that would disprove each one. High CPU may be cause, effect, or unrelated background work. A dependency error may originate in networking, capacity, authorization, or the caller’s deadline.

## Preserve evidence

Save query links, identifiers, representative traces, and bounded diagnostic captures. Avoid copying secrets or personal data into incident notes. Record the time and author of every mitigation.

## Confirm recovery

Validate the original user-facing symptom and its supporting signals over a stable window. A green health endpoint alone does not prove queues drained or tail latency recovered.
