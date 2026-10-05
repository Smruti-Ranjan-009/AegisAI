# Kafka Event Backbone

## Implemented architecture

```text
OpenTelemetry Demo                 Phase 1 JSONL capture
        |                                   |
        v                                   v
OpenTelemetry Collector               Replay producer
        |                                   |
        +---------------+-------------------+
                        v
                  telemetry.raw
                        |
         aegis-telemetry-processor-v1
                        |
                Telemetry worker
                 /             \
                v               v
    telemetry.processed     telemetry.dlq
```

Phase 2 adds transport, validation, metadata normalization, and failure
routing. The worker does not calculate ML features or implement incident logic.

## Local Kafka topology

The root Compose pins `apache/kafka:4.3.1`. One node acts as both broker and
controller in KRaft mode; ZooKeeper is absent. Host clients use
`localhost:9092`, containers use `kafka:19092`, and the unexposed controller
listener uses `19093`. The named `aegis-backbone` network also permits the
Phase 2 Collector overlay to reach Kafka without `host.docker.internal`.

Because the Collector joins both the demo network and `aegis-backbone`, the
overlay binds its OTLP gRPC and HTTP receivers to all container interfaces.
This keeps SDK traffic on the demo network reachable while Kafka uses the
backbone network.

This is a resource-conscious development topology. Production should use
multiple brokers/controllers or a managed service, secured listeners,
authorization, monitoring, capacity planning, and durable operational
procedures. Local PLAINTEXT listeners are not the production security model.

Kafka data lives in `aegis-kafka-data`. `docker compose down` preserves it;
`docker compose down -v` irreversibly deletes it. Automatic topic creation is
disabled at both broker and producer/exporter levels.

## Topic catalog

| Topic | Partitions | Replicas | Retention | Cleanup |
| --- | ---: | ---: | ---: | --- |
| `telemetry.raw` | 3 | 1 | 24 hours | delete |
| `telemetry.processed` | 3 | 1 | 24 hours | delete |
| `telemetry.dlq` | 1 | 1 | 7 days | delete |

The one-shot `kafka-init` service loads `infrastructure/kafka/topics.json`,
creates missing topics, then verifies partition count, replication factor,
retention, and cleanup policy. It fails on incompatible existing topics.

## Records and partitioning

Collector and replay values on `telemetry.raw` are unmodified OTLP JSON.
Required headers identify event type, schema version, and signal. Replay adds
the Phase 1 run ID, scenario, and label.

The worker extracts every unique `service.name` from `resourceMetrics`,
`resourceLogs`, or `resourceSpans`. Processed records use the alphabetically
first service name as their Kafka key, which provides service-local partition
ordering. Records without a service name use their deterministic event ID.

Processed IDs are SHA-256 hashes of `telemetry.raw:<partition>:<offset>`.
Reprocessing the same source record therefore produces the same idempotency
key, although deterministic IDs alone do not eliminate duplicates.

## Delivery semantics

The pipeline provides:

```text
at-least-once consumption
+ manual source offset commits
+ idempotent producers with acks=all
+ deterministic processed event IDs
```

It does not claim end-to-end exactly-once delivery. Consumer auto-commit and
auto-offset-store are disabled. The worker commits only after the processed
record or its DLQ envelope receives a delivery acknowledgement. If neither
publication succeeds, the source offset remains uncommitted.

Producer delivery is bounded, uses zstd compression, and checks callbacks.
Transient publication errors use three attempts by default with exponential
backoff. Permanent input errors—missing headers, unsupported signals, invalid
UTF-8/JSON, or invalid OTLP structure—go directly to the DLQ. Stack traces stay
in worker logs rather than event bodies.

The Collector 0.159.0 exporters use `required_acks: -1`, zstd, a bounded
60-second retry window, and 500-batch in-memory queues. These queues are not
durable across Collector termination.

## Contracts and evolution

Contracts live in `shared/contracts/events`. Phase 2 establishes immutable
schema version `1`; a breaking change requires a new version and a consumer
migration window. No schema registry is deployed. JSON Schema validation is
performed before worker publication.

## Commands

Install telemetry-service dependencies into the active Python environment:

```powershell
conda activate aegis
python -m pip install -r services\telemetry-service\requirements.txt
```

Operate Kafka and the worker:

```powershell
python scripts\kafka_pipeline.py start
python scripts\kafka_pipeline.py status
python scripts\kafka_pipeline.py topics
python scripts\kafka_pipeline.py replay --run <run-id> --limit 30
python scripts\kafka_pipeline.py consume --topic telemetry.processed --limit 5
python scripts\kafka_pipeline.py consume --topic telemetry.dlq --limit 5
python scripts\kafka_pipeline.py stop
```

Run the external demo in live streaming mode only after Kafka is running:

```powershell
python scripts\kafka_pipeline.py stream-start
python scripts\kafka_pipeline.py stream-status
python scripts\kafka_pipeline.py stream-stop
```

Phase 1 capture commands remain unchanged. Capture and streaming overlays are
separate modes and should not be started concurrently under the shared demo
project name.

## Graceful shutdown and troubleshooting

The worker handles SIGINT/SIGTERM, stops polling, flushes its producer, closes
the consumer, and leaves the group cleanly. Useful structured logs include
consumer start/stop, assignments, processed records, and DLQ routing; raw OTLP
payloads are not logged.

- If the CLI says Docker is unreachable, start Docker Desktop manually.
- If topic provisioning fails, inspect `docker compose logs kafka kafka-init`.
- If the worker is not consuming, inspect `docker compose logs telemetry-worker`.
- If streaming fails, confirm `aegis-backbone` exists and Kafka is healthy.
- Existing topics with incompatible partitions/configuration are rejected;
  use the destructive reset only when losing local Kafka data is acceptable.

```powershell
python scripts\kafka_pipeline.py stop
python scripts\kafka_pipeline.py reset --yes
```
