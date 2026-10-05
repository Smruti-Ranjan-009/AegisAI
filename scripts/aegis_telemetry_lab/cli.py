from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .capture import format_summary, run_capture
from .config import LabConfig, Timings, load_config
from .demo import DemoEnvironment
from .errors import LabError
from .flags import patch_variants
from .scenarios import Scenario, get_scenario, load_scenarios, managed_baselines
from .validation import resolve_run_directory, validate_capture


def _add_timing_arguments(parser: argparse.ArgumentParser, config: LabConfig) -> None:
    parser.add_argument("--warmup", type=int, default=config.timings.warmup_seconds)
    parser.add_argument("--duration", type=int, default=config.timings.capture_seconds)
    parser.add_argument(
        "--fault-propagation",
        type=int,
        default=config.timings.fault_propagation_seconds,
    )
    parser.add_argument(
        "--flush-delay",
        type=int,
        default=config.timings.collector_flush_seconds,
    )


def _timings(arguments: argparse.Namespace) -> Timings:
    return Timings(
        warmup_seconds=arguments.warmup,
        capture_seconds=arguments.duration,
        fault_propagation_seconds=arguments.fault_propagation,
        collector_flush_seconds=arguments.flush_delay,
    )


def build_parser(config: LabConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and validate labeled raw telemetry with OpenTelemetry Demo 3.1.0."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup", help="Prepare and verify the pinned upstream runtime clone.")
    subparsers.add_parser("start", help="Start the isolated minimal telemetry lab.")
    subparsers.add_parser("status", help="Show telemetry lab container status.")
    subparsers.add_parser("scenarios", help="List verified declarative scenarios.")

    run_parser = subparsers.add_parser("run", help="Capture one labeled scenario.")
    run_parser.add_argument("--scenario", required=True)
    _add_timing_arguments(run_parser, config)

    run_all_parser = subparsers.add_parser("run-all", help="Capture each declared scenario.")
    _add_timing_arguments(run_all_parser, config)

    validate_parser = subparsers.add_parser("validate", help="Validate an existing capture run.")
    validate_parser.add_argument("--run", required=True, dest="run_id")

    subparsers.add_parser("stop", help="Stop and remove only telemetry lab containers.")

    clean_parser = subparsers.add_parser("clean", help="Remove generated lab data explicitly.")
    clean_parser.add_argument(
        "--captures", action="store_true", help="Remove all raw capture runs."
    )
    clean_parser.add_argument(
        "--runtime", action="store_true", help="Remove the runtime clone/config."
    )
    clean_parser.add_argument(
        "--all", action="store_true", help="Remove captures and runtime data."
    )
    clean_parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    return parser


def _confirm(message: str) -> bool:
    return input(f"{message} Type 'yes' to continue: ").strip().lower() == "yes"


def _ensure_within_repo(config: LabConfig, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(config.repo_root.resolve())
    except ValueError as exc:
        raise LabError(f"Refusing to remove path outside repository: {resolved}") from exc
    return resolved


def _clean(config: LabConfig, demo: DemoEnvironment, arguments: argparse.Namespace) -> None:
    captures = arguments.captures or arguments.all
    runtime = arguments.runtime or arguments.all
    if not captures and not runtime:
        raise LabError("Choose --captures, --runtime, or --all. Nothing was removed.")
    demo.check_docker_daemon()
    if demo.has_running_project_containers():
        raise LabError("Stop the telemetry lab before cleaning generated files.")

    targets = []
    if captures:
        targets.append("all directories under data/raw")
    if runtime:
        targets.append(str(config.runtime_dir.parent.relative_to(config.repo_root)))
    if not arguments.yes and not _confirm("Remove " + " and ".join(targets) + "?"):
        print("Cleanup cancelled.")
        return

    if captures:
        raw_root = _ensure_within_repo(config, config.raw_data_dir)
        if raw_root.exists():
            for child in raw_root.iterdir():
                if child.name == ".gitkeep":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    if runtime:
        runtime_root = _ensure_within_repo(config, config.repo_root / ".runtime")
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
    print("Cleanup complete.")


def _prepare_started_lab(
    config: LabConfig,
    demo: DemoEnvironment,
    scenarios: dict[str, Scenario],
) -> None:
    demo.setup()
    demo.verify_scenarios(scenarios)
    demo.reset_runtime_flag_file()
    patch_variants(config.runtime_flag_file, managed_baselines(scenarios))
    demo.start()
    for flag_name, baseline in managed_baselines(scenarios).items():
        demo.verify_flag(flag_name, baseline)


def execute(arguments: argparse.Namespace, config: LabConfig) -> int:
    scenarios = load_scenarios(config.scenarios_file)
    demo = DemoEnvironment(config)

    if arguments.command == "setup":
        commit = demo.setup()
        demo.verify_scenarios(scenarios)
        print(f"OpenTelemetry Demo {config.otel_demo_version} ready at {commit}.")
    elif arguments.command == "start":
        _prepare_started_lab(config, demo, scenarios)
        print(demo.status())
    elif arguments.command == "status":
        print(demo.status())
    elif arguments.command == "scenarios":
        if config.demo_dir.exists():
            demo.verify_checkout()
            demo.verify_scenarios(scenarios)
        for scenario in scenarios.values():
            flag = scenario.feature_flag
            flag_text = (
                f"{flag.name}={flag.variant} (baseline {flag.baseline_variant})"
                if flag
                else "none"
            )
            affected = ", ".join(scenario.expected_affected_services) or "none"
            print(
                f"{scenario.name}: label={scenario.label}; flag={flag_text}; "
                f"affected={affected}"
            )
    elif arguments.command == "run":
        scenario = get_scenario(scenarios, arguments.scenario)
        result = run_capture(config, demo, scenarios, scenario, _timings(arguments))
        print(format_summary(result, config.raw_data_dir))
    elif arguments.command == "run-all":
        for scenario in scenarios.values():
            result = run_capture(config, demo, scenarios, scenario, _timings(arguments))
            print(format_summary(result, config.raw_data_dir))
            print()
    elif arguments.command == "validate":
        run_dir = resolve_run_directory(config.raw_data_dir, arguments.run_id, must_exist=True)
        result = validate_capture(run_dir)
        print(format_summary(result, config.raw_data_dir))
    elif arguments.command == "stop":
        demo.stop()
        print("Telemetry lab stopped; project containers and network removed.")
    elif arguments.command == "clean":
        _clean(config, demo, arguments)
    else:
        raise LabError(f"Unsupported command: {arguments.command}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        config = load_config()
        parser = build_parser(config)
        arguments = parser.parse_args(argv)
        return execute(arguments, config)
    except LabError as exc:
        print(f"telemetry-lab: error: {exc}", file=sys.stderr)
        return 2
