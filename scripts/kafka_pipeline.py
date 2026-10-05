"""Developer CLI for the Phase 2 Kafka telemetry pipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_SERVICE = REPO_ROOT / "services" / "telemetry-service"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(TELEMETRY_SERVICE))

from app.messaging.admin import load_topic_specs, provision_topics, topic_status  # noqa: E402
from app.messaging.config import KafkaSettings  # noqa: E402
from app.messaging.inspect import consume_records  # noqa: E402
from app.messaging.replay import replay_capture  # noqa: E402
from scripts.aegis_telemetry_lab.config import load_config as load_lab_config  # noqa: E402
from scripts.aegis_telemetry_lab.demo import DemoEnvironment  # noqa: E402
from scripts.aegis_telemetry_lab.flags import patch_variants  # noqa: E402
from scripts.aegis_telemetry_lab.scenarios import (  # noqa: E402
    load_scenarios,
    managed_baselines,
)
from scripts.aegis_telemetry_lab.validation import (  # noqa: E402
    resolve_run_directory,
    validate_capture,
)


class CliError(RuntimeError):
    pass


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise CliError(f"Could not run {command[0]!r}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise CliError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result.stdout.strip()


def check_docker() -> None:
    if shutil.which("docker") is None:
        raise CliError("Docker CLI was not found on PATH.")
    try:
        run(["docker", "compose", "version"])
        run(["docker", "info"])
    except CliError as exc:
        raise CliError("Docker Desktop/daemon is not reachable. Start it and retry.") from exc


def compose(*arguments: str) -> str:
    return run(["docker", "compose", *arguments])


def start() -> None:
    check_docker()
    compose(
        "up",
        "--detach",
        "--build",
        "--wait",
        "--wait-timeout",
        "180",
        "kafka",
        "kafka-init",
        "telemetry-worker",
    )
    print(compose("ps", "kafka", "kafka-init", "telemetry-worker"))


def format_replay(result: object) -> str:
    counts = result.counts  # type: ignore[attr-defined]
    return "\n".join(
        [
            f"Run ID: {result.run_id}",  # type: ignore[attr-defined]
            f"Scenario: {result.scenario}",  # type: ignore[attr-defined]
            f"Label: {result.label}",  # type: ignore[attr-defined]
            "",
            "Published:",
            f"metrics: {counts['metrics']}",
            f"logs: {counts['logs']}",
            f"traces: {counts['traces']}",
            "",
            f"Total: {result.total}",  # type: ignore[attr-defined]
            "Target: telemetry.raw",
            "Delivery failures: 0",
        ]
    )


def _stream_environment() -> tuple[dict[str, str], DemoEnvironment]:
    lab = load_lab_config(REPO_ROOT)
    demo = DemoEnvironment(lab)
    scenarios = load_scenarios(lab.scenarios_file)
    demo.setup()
    demo.check_docker_daemon()
    demo.verify_scenarios(scenarios)
    demo.reset_runtime_flag_file()
    patch_variants(lab.runtime_flag_file, managed_baselines(scenarios))
    environment = os.environ.copy()
    environment.update(
        {
            "AEGIS_FLAGD_DIR": str(lab.runtime_flag_dir.resolve()),
            "OTEL_COLLECTOR_CONFIG_EXTRAS": str(
                (lab.infrastructure_dir / "collector/aegis-kafka-config.yml").resolve()
            ),
            "DEMO_VERSION": lab.otel_demo_version,
            "IMAGE_VERSION": lab.otel_demo_version,
            "ENVOY_PORT": str(lab.frontend_proxy_port),
            "ENVOY_ADMIN_PORT": str(lab.envoy_admin_port),
            "LOCUST_AUTOSTART": "true",
        }
    )
    return environment, demo


def stream_compose(*arguments: str, prepare: bool = True) -> str:
    lab = load_lab_config(REPO_ROOT)
    if prepare:
        environment, _ = _stream_environment()
    else:
        environment = os.environ.copy()
        environment.update(
            {
                "AEGIS_FLAGD_DIR": str(lab.runtime_flag_dir.resolve()),
                "OTEL_COLLECTOR_CONFIG_EXTRAS": str(
                    (lab.infrastructure_dir / "collector/aegis-kafka-config.yml").resolve()
                ),
                "DEMO_VERSION": lab.otel_demo_version,
                "IMAGE_VERSION": lab.otel_demo_version,
                "ENVOY_PORT": str(lab.frontend_proxy_port),
                "ENVOY_ADMIN_PORT": str(lab.envoy_admin_port),
            }
        )
    command = [
        "docker",
        "compose",
        "--project-name",
        lab.compose_project,
        "--env-file",
        str(lab.upstream_env_file),
        "--file",
        str(lab.upstream_compose_file),
        "--file",
        str(lab.infrastructure_dir / "compose.kafka.yml"),
        *arguments,
    ]
    return run(command, env=environment)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the AegisAI Kafka pipeline.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start", help="Start Kafka, provision topics, and start the worker.")
    commands.add_parser("status", help="Show root Compose service status.")
    commands.add_parser("topics", help="Verify and list Phase 2 topics.")

    replay_parser = commands.add_parser("replay", help="Replay a Phase 1 capture.")
    replay_parser.add_argument("--run", required=True, dest="run_id")
    replay_parser.add_argument("--limit", type=int)

    consume_parser = commands.add_parser("consume", help="Inspect topic records.")
    consume_parser.add_argument(
        "--topic", required=True, choices=["telemetry.raw", "telemetry.processed", "telemetry.dlq"]
    )
    consume_parser.add_argument("--limit", type=int, default=5)
    consume_parser.add_argument("--timeout", type=float, default=15)

    commands.add_parser("stream-start", help="Start the OTel Demo in Kafka streaming mode.")
    commands.add_parser("stream-status", help="Show OTel streaming container status.")
    commands.add_parser("stream-stop", help="Stop the OTel streaming workload.")
    commands.add_parser("stop", help="Stop root Kafka/worker services and preserve data.")
    reset_parser = commands.add_parser("reset", help="Destructively remove the Kafka volume.")
    reset_parser.add_argument("--yes", action="store_true")
    return parser


def execute(arguments: argparse.Namespace) -> None:
    settings = KafkaSettings.from_environment()
    if arguments.command == "start":
        start()
    elif arguments.command == "status":
        check_docker()
        print(compose("ps", "--all"))
    elif arguments.command == "topics":
        provision_topics(settings, load_topic_specs())
        print(json.dumps(topic_status(settings, load_topic_specs()), indent=2))
    elif arguments.command == "replay":
        lab = load_lab_config(REPO_ROOT)
        run_dir = resolve_run_directory(lab.raw_data_dir, arguments.run_id, must_exist=True)
        validate_capture(run_dir)
        if arguments.limit is not None and arguments.limit < 1:
            raise CliError("--limit must be a positive integer")
        print(format_replay(replay_capture(run_dir, settings, limit=arguments.limit)))
    elif arguments.command == "consume":
        if arguments.limit < 1 or arguments.timeout <= 0:
            raise CliError("--limit and --timeout must be positive")
        records = consume_records(
            settings,
            arguments.topic,
            limit=arguments.limit,
            timeout_seconds=arguments.timeout,
        )
        print(json.dumps(records, indent=2))
        print(f"Records read: {len(records)}")
    elif arguments.command == "stream-start":
        check_docker()
        stream_compose(
            "up",
            "--detach",
            "--pull",
            "always",
            "--no-build",
            "--wait",
            "--wait-timeout",
            "600",
        )
        print(stream_compose("ps", "--all", prepare=False))
    elif arguments.command == "stream-status":
        check_docker()
        print(stream_compose("ps", "--all", prepare=False))
    elif arguments.command == "stream-stop":
        check_docker()
        stream_compose("down", "--remove-orphans", prepare=False)
        print("OpenTelemetry streaming workload stopped.")
    elif arguments.command == "stop":
        check_docker()
        compose("down", "--remove-orphans")
        print("Kafka pipeline stopped; named Kafka data volume preserved.")
    elif arguments.command == "reset":
        check_docker()
        if not arguments.yes:
            confirmation = input("Delete all local Kafka data? Type 'yes' to continue: ")
            if confirmation.strip().lower() != "yes":
                print("Reset cancelled.")
                return
        compose("down", "--volumes", "--remove-orphans")
        print("Kafka pipeline stopped and the Kafka data volume was deleted.")


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        execute(arguments)
    except Exception as exc:
        print(f"kafka-pipeline: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
