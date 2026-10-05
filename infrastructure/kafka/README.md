# Local Kafka backbone

Phase 2 uses the official `apache/kafka:4.3.1` image as a single combined
broker/controller in KRaft mode. Topics are declared in `topics.json` and are
created and verified by the one-shot `kafka-init` service. Automatic topic
creation is disabled.

The `aegis-backbone` network provides `kafka:19092` to containers while the
host uses `localhost:9092`. Port `19093` is controller-only and is not exposed.
The named `aegis-kafka-data` volume survives `docker compose down`.

This plaintext, single-node topology is for local development only. Production
requires secured listeners and multiple brokers/controllers or a managed
Kafka service.
