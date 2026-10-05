# `telemetry.raw` record contract — version 1

The Kafka value is an unmodified OTLP JSON object. AegisAI intentionally does
not duplicate the full OpenTelemetry schema.

Required Kafka headers:

| Header | Value |
| --- | --- |
| `aegis.event_type` | `telemetry.raw` |
| `aegis.schema_version` | `1` |
| `aegis.signal` | `metrics`, `logs`, or `traces` |
| `content-type` | `application/json` |

Replay producers additionally set `aegis.run_id`, `aegis.scenario`, and
`aegis.label`. The expected OTLP root is `resourceMetrics`, `resourceLogs`, or
`resourceSpans`, according to the signal header.

The Collector is the live producer and the Phase 1 replay tool is the offline
producer. `aegis-telemetry-processor-v1` is the active consumer group.
