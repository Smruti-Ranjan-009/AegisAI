from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from typing import Any

from .audit import registry_audit
from .config import LifecycleConfig
from .errors import LifecycleError
from .importers import import_anomaly, import_classifier
from .promotion import promote, rollback
from .registry import resolve_champion, spec_for
from .tracking import configure_tracking, initialize
from .verification import verify_alias


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="aegis-lifecycle")
    root.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    root.add_argument("--debug", action="store_true", help="Show unexpected tracebacks")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize local experiments and registry storage")
    anomaly = commands.add_parser("import-anomaly", help="Import a frozen Phase 5 artifact")
    anomaly.add_argument("--model-id", default=spec_for("anomaly").default_model_id)
    classifier = commands.add_parser(
        "import-classifier", help="Import a frozen Phase 6 artifact"
    )
    classifier.add_argument("--model-id", default=spec_for("classifier").default_model_id)
    for name in ("promote", "rollback"):
        action = commands.add_parser(name, help=f"{name.title()} a registry model version")
        action.add_argument("--model", choices=("anomaly", "classifier"), required=True)
        action.add_argument("--version", required=True)
        action.add_argument("--reason", default="")
    verify = commands.add_parser("verify", help="Verify an alias and smoke inference")
    verify.add_argument("--model", choices=("anomaly", "classifier"), required=True)
    verify.add_argument("--alias", default="champion")
    resolve = commands.add_parser("resolve", help="Resolve the champion model URI")
    resolve.add_argument("--model", choices=("anomaly", "classifier"), required=True)
    commands.add_parser("audit", help="Show compact registry and alias history")
    return root


def execute(arguments: argparse.Namespace, config: LifecycleConfig) -> dict[str, Any]:
    if arguments.command == "init":
        return initialize(config)
    client = configure_tracking(config)
    if arguments.command == "import-anomaly":
        return import_anomaly(client, config, arguments.model_id)
    if arguments.command == "import-classifier":
        return import_classifier(client, config, arguments.model_id)
    if arguments.command == "promote":
        return promote(client, config, arguments.model, arguments.version, arguments.reason)
    if arguments.command == "rollback":
        return rollback(client, config, arguments.model, arguments.version, arguments.reason)
    if arguments.command == "verify":
        started = time.perf_counter()
        result = verify_alias(client, config, arguments.model, arguments.alias)
        result["verification_duration_seconds"] = time.perf_counter() - started
        return result
    if arguments.command == "resolve":
        started = time.perf_counter()
        result = resolve_champion(client, arguments.model)
        result["lookup_duration_seconds"] = time.perf_counter() - started
        return result
    return registry_audit(client, config)


def _render(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return
    for key, value in result.items():
        if isinstance(value, dict | list):
            print(f"{key}: {json.dumps(value, sort_keys=True, default=str)}")
        else:
            print(f"{key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = parser()
    arguments = argument_parser.parse_args(argv)
    try:
        _render(execute(arguments, LifecycleConfig.from_environment()), arguments.json)
        return 0
    except LifecycleError as exc:
        if arguments.json:
            print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        else:
            print(f"aegis-lifecycle: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary normalizes third-party failures
        if arguments.debug:
            raise
        failure = LifecycleError("registry_failure", str(exc))
        if arguments.json:
            print(json.dumps(failure.as_dict(), sort_keys=True), file=sys.stderr)
        else:
            print(f"aegis-lifecycle: {failure}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
