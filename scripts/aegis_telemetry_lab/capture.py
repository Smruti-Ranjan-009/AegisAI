from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

from .config import LabConfig, Timings
from .demo import DemoEnvironment
from .errors import LabError
from .flags import atomic_write_json, patch_variants, temporary_patch
from .scenarios import Scenario, managed_baselines
from .validation import CaptureValidation, resolve_run_directory, validate_capture


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def generate_run_id(
    raw_root: Path,
    scenario_name: str,
    *,
    now: Callable[[], datetime] = utc_now,
    token_hex: Callable[[int], str] = secrets.token_hex,
) -> str:
    timestamp = now().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    scenario_slug = scenario_name.replace("_", "-")
    for _ in range(100):
        run_id = f"{timestamp}-{scenario_slug}-{token_hex(3)}"
        if not (raw_root / run_id).exists():
            return run_id
    raise LabError("Could not generate a unique run ID after 100 attempts.")


def _validate_timing(name: str, value: int, *, allow_zero: bool = True) -> None:
    minimum = 0 if allow_zero else 1
    if value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise LabError(f"{name} must be a {qualifier} integer.")


def run_capture(
    config: LabConfig,
    demo: DemoEnvironment,
    scenarios: dict[str, Scenario],
    scenario: Scenario,
    timings: Timings,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = utc_now,
) -> CaptureValidation:
    _validate_timing("warmup", timings.warmup_seconds)
    _validate_timing("duration", timings.capture_seconds, allow_zero=False)
    _validate_timing("fault propagation delay", timings.fault_propagation_seconds)
    _validate_timing("collector flush delay", timings.collector_flush_seconds)

    demo.ensure_started()
    commit = demo.verify_checkout()
    demo.verify_scenarios(scenarios)

    baselines = managed_baselines(scenarios)
    patch_variants(config.runtime_flag_file, baselines)
    for flag_name, baseline in baselines.items():
        demo.verify_flag(flag_name, baseline)

    if timings.warmup_seconds:
        sleeper(timings.warmup_seconds)
    traffic_services = demo.verify_traffic()

    run_id = generate_run_id(config.raw_data_dir, scenario.name, now=now)
    run_dir = resolve_run_directory(config.raw_data_dir, run_id)
    run_dir.mkdir(parents=True, exist_ok=False)

    feature_flag = scenario.feature_flag
    changes = {feature_flag.name: feature_flag.variant} if feature_flag else {}
    patch_context = temporary_patch(config.runtime_flag_file, changes) if changes else nullcontext()
    collector_active = False
    started_at: datetime | None = None
    ended_at: datetime | None = None

    try:
        with patch_context:
            if feature_flag:
                demo.verify_flag(feature_flag.name, feature_flag.variant)
                if timings.fault_propagation_seconds:
                    sleeper(timings.fault_propagation_seconds)

            demo.recreate_collector(run_dir)
            collector_active = True
            started_at = now()
            sleeper(timings.capture_seconds)
            ended_at = now()
            if timings.collector_flush_seconds:
                sleeper(timings.collector_flush_seconds)
            demo.stop_collector(run_dir)
            collector_active = False
    finally:
        collector_error: LabError | None = None
        if collector_active:
            try:
                demo.stop_collector(run_dir)
            except LabError as exc:
                collector_error = exc
        try:
            patch_variants(config.runtime_flag_file, baselines)
            for flag_name, baseline in baselines.items():
                demo.verify_flag(flag_name, baseline)
        finally:
            demo.restore_idle_collector()
        if collector_error is not None:
            raise collector_error

    if started_at is None or ended_at is None:
        raise LabError("Capture ended before timestamps could be recorded.")

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario": scenario.name,
        "label": scenario.label,
        "started_at_utc": format_utc(started_at),
        "ended_at_utc": format_utc(ended_at),
        "duration_seconds": timings.capture_seconds,
        "otel_demo_version": config.otel_demo_version,
        "upstream_git_commit": commit,
        "feature_flag": (
            {
                "name": feature_flag.name,
                "variant": feature_flag.variant,
                "baseline_variant": feature_flag.baseline_variant,
                "restored": True,
            }
            if feature_flag
            else None
        ),
        "expected_affected_services": list(scenario.expected_affected_services),
        "traffic_services_observed_before_capture": list(traffic_services),
        "signals": {
            "metrics": "metrics.jsonl",
            "logs": "logs.jsonl",
            "traces": "traces.jsonl",
        },
    }
    atomic_write_json(run_dir / "manifest.json", manifest)
    return validate_capture(run_dir)


def format_summary(result: CaptureValidation, raw_root: Path) -> str:
    run_dir = raw_root / result.run_id
    lines = [
        f"Run ID: {result.run_id}",
        f"Scenario: {result.scenario}",
        f"Label: {result.label}",
        "",
        f"Metrics batches: {result.signals['metrics'].batches}",
        f"Trace batches: {result.signals['traces'].batches}",
        f"Log batches: {result.signals['logs'].batches}",
        "",
        "Services observed:",
    ]
    lines.extend(f"- {service}" for service in result.services)
    lines.extend(
        [
            "",
            "Files:",
            str(run_dir / "metrics.jsonl"),
            str(run_dir / "traces.jsonl"),
            str(run_dir / "logs.jsonl"),
            str(run_dir / "manifest.json"),
            "",
            "Validation: PASS",
        ]
    )
    return "\n".join(lines)
