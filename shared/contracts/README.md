# Shared Contracts

Phase 2 establishes versioned Kafka contracts. Schema version `1` is immutable;
breaking changes require a new version and a migration period in which consumers
can understand both versions.

| Topic | Producer | Consumer | Value | Key | Retention |
| --- | --- | --- | --- | --- | --- |
| `telemetry.raw` | OTel Collector / replay | telemetry-worker | OTLP JSON plus required headers | Collector default / replay run ID | 24 hours |
| `telemetry.processed` | telemetry-worker | Future ML/incident processing | `telemetry-processed-v1.schema.json` | Primary service name, otherwise event ID | 24 hours |
| `telemetry.dlq` | telemetry-worker | Manual operational inspection | `telemetry-dlq-v1.schema.json` | Deterministic source event ID | 7 days |

Delivery is at least once: the consumer commits manually only after a processed
or DLQ publication is acknowledged. Producers are idempotent and processed IDs
are deterministic, but this is not an end-to-end exactly-once guarantee.

Phase 4 adds immutable offline table contracts under `shared/contracts/ml/`:

- `service-window-features-v1.md`
- `metric-window-features-v1.md`

Their ordered machine-readable column catalog lives with the independently
installable feature package at `ml/feature_engineering/feature_catalog_v1.json`.
