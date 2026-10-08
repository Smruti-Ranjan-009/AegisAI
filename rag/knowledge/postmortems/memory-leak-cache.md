---
title: Synthetic Postmortem — Unbounded Cache Memory Growth
document_type: postmortem
version: 1
services: [rag-service, platform]
incident_types: [memory_leak, service_failure]
synthetic: true
---
# Synthetic Postmortem: Unbounded Cache Memory Growth

This fictional exercise models an unbounded request cache; it is not a production record.

## Impact

RAG service replicas restarted repeatedly for 41 minutes. Health checks intermittently failed, although Phase 8 ingestion data was unaffected.

## Timeline

Memory began climbing after a configuration rollout. The first container exceeded its limit at 14:12. Responders rolled back at 14:29 and completed a controlled restart by 14:38.

## Root cause

A request cache had no entry or size bound after the configuration changed its expiration policy. High-cardinality request keys retained payload objects.

## Corrective actions

Enforce count and byte limits, test eviction behavior, publish cache metrics, and add a release check for monotonic memory growth under steady load.
