# AegisAI telemetry lab

This directory contains only AegisAI-owned configuration for the offline
telemetry dataset laboratory. The official OpenTelemetry Demo source is cloned
at runtime into `.runtime/opentelemetry-demo` and is never vendored here.

The lab is pinned to OpenTelemetry Demo `3.1.0`, commit
`dedc0178918e260823323b8d95005a8cb924b007`. Only upstream `compose.yaml` is
used. `compose.full.yaml`, `compose.observability.yaml`, and
`compose.extras.yaml` are not used.

The upstream minimal workload includes PostgreSQL and Valkey because its demo
application needs them. They are isolated internal workload dependencies; they
are not AegisAI production persistence and do not alter the Phase 0 Compose
stack.

`compose.capture.yml` adds the writable capture mount, an isolated runtime copy
of the flag configuration, and a dedicated network. The Collector extras file
preserves upstream's debug and span-metrics exporters and adds separate JSONL
file exporters for metrics, logs, and traces.

Phase 2 adds `compose.kafka.yml` and `collector/aegis-kafka-config.yml` as a
separate mode. It connects only the Collector to the external
`aegis-backbone` network and publishes OTLP JSON to `telemetry.raw`. It does
not alter or replace capture mode.

Use `python scripts\telemetry_lab.py --help` from the repository root. Full
operating instructions and the dataset contract are in
`docs/telemetry-dataset.md`.
