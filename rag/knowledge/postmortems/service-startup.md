---
title: Synthetic Postmortem — Invalid Configuration Prevented Startup
document_type: postmortem
version: 1
services: [telemetry-service, platform]
incident_types: [service_failure]
synthetic: true
---
# Synthetic Postmortem: Invalid Configuration Prevented Startup

This fictional exercise models a failed configuration rollout; it is not a production record.

## Impact

A deployment left insufficient ready telemetry replicas for 17 minutes. Producers buffered data locally; no confirmed data loss occurred.

## Timeline

The rollout began at 09:00. New pods failed startup validation at 09:02, but rollout automation continued replacing capacity. The team paused rollout at 09:09 and restored the prior configuration at 09:15.

## Root cause

A renamed environment variable passed review because the deployment test checked template rendering but not application startup. The rollout policy allowed too much simultaneous unavailability.

## Corrective actions

Run the container startup check in CI, validate required configuration at deployment time, and tighten minimum-ready capacity during rollout.
