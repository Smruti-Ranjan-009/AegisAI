from __future__ import annotations

import argparse
import json
import sys

from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic, ResourceType

from .config import KafkaSettings, TopicSpec, load_topic_specs


def _admin(settings: KafkaSettings) -> AdminClient:
    return AdminClient(
        {
            "bootstrap.servers": settings.bootstrap_servers,
            "client.id": "aegis-topic-admin",
            "allow.auto.create.topics": False,
        }
    )


def _verify_topic(admin: AdminClient, spec: TopicSpec) -> None:
    metadata = admin.list_topics(topic=spec.name, timeout=15)
    topic = metadata.topics.get(spec.name)
    if topic is None or topic.error is not None:
        detail = topic.error if topic else "missing"
        raise RuntimeError(f"Topic {spec.name} is unavailable: {detail}")
    if len(topic.partitions) != spec.partitions:
        raise RuntimeError(
            f"Topic {spec.name} has {len(topic.partitions)} partitions; expected {spec.partitions}"
        )
    replica_counts = {len(partition.replicas) for partition in topic.partitions.values()}
    if replica_counts != {spec.replication_factor}:
        raise RuntimeError(
            f"Topic {spec.name} has replication counts {sorted(replica_counts)}; "
            f"expected {spec.replication_factor}"
        )
    resource = ConfigResource(ResourceType.TOPIC, spec.name)
    actual = admin.describe_configs([resource])[resource].result(timeout=15)
    for key, expected in spec.config.items():
        value = actual[key].value
        if value != expected:
            raise RuntimeError(
                f"Topic {spec.name} config {key}={value!r}; expected {expected!r}"
            )


def provision_topics(settings: KafkaSettings, specs: tuple[TopicSpec, ...]) -> None:
    admin = _admin(settings)
    metadata = admin.list_topics(timeout=15)
    missing = [spec for spec in specs if spec.name not in metadata.topics]
    if missing:
        futures = admin.create_topics(
            [
                NewTopic(
                    spec.name,
                    num_partitions=spec.partitions,
                    replication_factor=spec.replication_factor,
                    config=spec.config,
                )
                for spec in missing
            ],
            operation_timeout=15,
        )
        for name, future in futures.items():
            future.result(timeout=20)
            print(f"Created topic {name}.")
    for spec in specs:
        _verify_topic(admin, spec)
        print(f"Verified topic {spec.name}.")


def topic_status(settings: KafkaSettings, specs: tuple[TopicSpec, ...]) -> list[dict[str, object]]:
    admin = _admin(settings)
    metadata = admin.list_topics(timeout=15)
    result = []
    for spec in specs:
        topic = metadata.topics.get(spec.name)
        result.append(
            {
                "topic": spec.name,
                "exists": bool(topic and topic.error is None),
                "partitions": len(topic.partitions) if topic and topic.error is None else 0,
                "replication_factor": spec.replication_factor,
                "config": spec.config,
            }
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision or inspect AegisAI Kafka topics.")
    parser.add_argument("--list", action="store_true", help="Print topic status as JSON.")
    arguments = parser.parse_args(argv)
    settings = KafkaSettings.from_environment()
    specs = load_topic_specs()
    if arguments.list:
        print(json.dumps(topic_status(settings, specs), indent=2))
    else:
        provision_topics(settings, specs)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"kafka-admin: error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
