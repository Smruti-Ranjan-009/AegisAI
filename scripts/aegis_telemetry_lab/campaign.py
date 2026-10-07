from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .capture import run_capture
from .config import LabConfig, Timings
from .demo import DemoEnvironment
from .errors import LabError
from .flags import atomic_write_json
from .scenarios import Scenario, managed_baselines
from .validation import validate_capture


@dataclass(frozen=True)
class CampaignPlan:
    name: str
    timings: Timings
    cooldown_seconds: int
    required_runs: dict[str, int]
    order: tuple[str, ...]
    restart_services: dict[str, tuple[str, ...]]


def _integer(mapping: dict[str, Any], name: str, *, minimum: int = 0) -> int:
    value = mapping.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise LabError(f"Campaign {name!r} must be an integer >= {minimum}.")
    return value


def load_campaign_plan(path: Path, scenarios: dict[str, Scenario]) -> CampaignPlan:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"Cannot read campaign plan {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise LabError("Campaign plan must be a schema-version-1 JSON object.")
    name = document.get("name")
    timings_data = document.get("timings")
    required = document.get("required_runs")
    order = document.get("order")
    recovery = document.get("recovery", {})
    if not isinstance(name, str) or not name:
        raise LabError("Campaign plan requires a non-empty name.")
    if not isinstance(timings_data, dict):
        raise LabError("Campaign plan requires a timings object.")
    if not isinstance(required, dict) or not required:
        raise LabError("Campaign plan requires non-empty required_runs.")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise LabError("Campaign plan order must be an array of scenario names.")

    required_runs: dict[str, int] = {}
    for scenario_name, count in required.items():
        if scenario_name not in scenarios:
            raise LabError(f"Campaign references unknown scenario {scenario_name!r}.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise LabError(f"Required count for {scenario_name!r} must be positive.")
        required_runs[scenario_name] = count
    if Counter(order) != Counter(required_runs):
        expected = {name: required_runs[name] for name in sorted(required_runs)}
        actual = dict(sorted(Counter(order).items()))
        raise LabError(f"Campaign order counts {actual} do not match required_runs {expected}.")

    restart_services: dict[str, tuple[str, ...]] = {}
    if not isinstance(recovery, dict):
        raise LabError("Campaign recovery must be an object.")
    for scenario_name, policy in recovery.items():
        if scenario_name == "after_fault":
            continue
        if scenario_name not in scenarios or not isinstance(policy, dict):
            raise LabError(f"Invalid recovery policy for {scenario_name!r}.")
        services = policy.get("restart_services", [])
        if not isinstance(services, list) or not all(
            isinstance(service, str) and service for service in services
        ):
            raise LabError(f"Recovery restart_services for {scenario_name!r} is invalid.")
        restart_services[scenario_name] = tuple(services)

    timings = Timings(
        warmup_seconds=_integer(timings_data, "warmup_seconds"),
        capture_seconds=_integer(timings_data, "capture_seconds", minimum=1),
        fault_propagation_seconds=_integer(timings_data, "fault_propagation_seconds"),
        collector_flush_seconds=_integer(timings_data, "collector_flush_seconds"),
    )
    return CampaignPlan(
        name=name,
        timings=timings,
        cooldown_seconds=_integer(timings_data, "cooldown_seconds"),
        required_runs=required_runs,
        order=tuple(order),
        restart_services=restart_services,
    )


def campaign_result_path(config: LabConfig, plan: CampaignPlan) -> Path:
    return config.runtime_dir / "campaigns" / f"{plan.name}-result.json"


def _new_result(plan: CampaignPlan) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign": plan.name,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "completed_at_utc": None,
        "status": "IN_PROGRESS",
        "timings": {
            "warmup_seconds": plan.timings.warmup_seconds,
            "capture_seconds": plan.timings.capture_seconds,
            "fault_propagation_seconds": plan.timings.fault_propagation_seconds,
            "collector_flush_seconds": plan.timings.collector_flush_seconds,
            "cooldown_seconds": plan.cooldown_seconds,
        },
        "required_runs": plan.required_runs,
        "accepted_runs": [],
        "rejected_attempts": [],
    }


def _load_progress(path: Path, plan: CampaignPlan) -> dict[str, Any]:
    if not path.exists():
        return _new_result(plan)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"Cannot resume campaign result {path}: {exc}") from exc
    if (
        result.get("campaign") != plan.name
        or result.get("timings") != _new_result(plan)["timings"]
        or result.get("required_runs") != plan.required_runs
    ):
        raise LabError("Existing campaign result does not match the requested plan and timings.")
    accepted = result.get("accepted_runs")
    rejected = result.get("rejected_attempts")
    if not isinstance(accepted, list) or not isinstance(rejected, list):
        raise LabError("Existing campaign result has invalid progress arrays.")
    return result


def _validated_progress(
    config: LabConfig, plan: CampaignPlan, result: dict[str, Any]
) -> tuple[list[dict[str, str]], Counter[str]]:
    accepted: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for item in result["accepted_runs"]:
        if not isinstance(item, dict) or not isinstance(item.get("run_id"), str):
            raise LabError("Campaign result contains an invalid accepted run entry.")
        validation = validate_capture(config.raw_data_dir / item["run_id"])
        if validation.scenario != item.get("scenario"):
            raise LabError(f"Campaign run {validation.run_id} scenario does not match progress.")
        if counts[validation.scenario] < plan.required_runs.get(validation.scenario, 0):
            accepted.append({"run_id": validation.run_id, "scenario": validation.scenario})
            counts[validation.scenario] += 1
    return accepted, counts


def run_campaign(
    config: LabConfig,
    demo: DemoEnvironment,
    scenarios: dict[str, Scenario],
    plan: CampaignPlan,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    output = campaign_result_path(config, plan)
    config.raw_data_dir.mkdir(parents=True, exist_ok=True)
    result = _load_progress(output, plan)
    accepted, counts = _validated_progress(config, plan, result)
    result["accepted_runs"] = accepted
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output, result)

    baselines = managed_baselines(scenarios)
    failures_before = len(result["rejected_attempts"])
    for scenario_name in plan.order:
        if counts[scenario_name] >= plan.required_runs[scenario_name]:
            continue
        scenario = scenarios[scenario_name]
        run_directories_before = {
            path.name for path in config.raw_data_dir.iterdir() if path.is_dir()
        }
        try:
            validation = run_capture(
                config,
                demo,
                scenarios,
                scenario,
                plan.timings,
                sleeper=sleeper,
            )
            for flag_name, baseline in baselines.items():
                demo.verify_flag(flag_name, baseline)
            for service in plan.restart_services.get(scenario_name, ()):
                demo.restart_service(service)
            if scenario.feature_flag:
                demo.verify_services_running(scenario.expected_affected_services)
                if plan.cooldown_seconds:
                    sleeper(plan.cooldown_seconds)
            entry = {"run_id": validation.run_id, "scenario": validation.scenario}
            result["accepted_runs"].append(entry)
            counts[scenario_name] += 1
        except LabError as exc:
            run_directories_after = {
                path.name for path in config.raw_data_dir.iterdir() if path.is_dir()
            }
            result["rejected_attempts"].append(
                {
                    "scenario": scenario_name,
                    "run_ids": sorted(run_directories_after - run_directories_before),
                    "error": str(exc),
                    "recorded_at_utc": datetime.now(UTC).isoformat(),
                }
            )
        atomic_write_json(output, result)

    complete = all(counts[name] >= count for name, count in plan.required_runs.items())
    result["status"] = "PASS" if complete else "FAIL"
    result["completed_at_utc"] = datetime.now(UTC).isoformat()
    result["accepted_counts"] = dict(sorted(counts.items()))
    atomic_write_json(output, result)
    if not complete:
        raise LabError(
            f"Campaign incomplete; see {output}. "
            f"New rejected attempts: {len(result['rejected_attempts']) - failures_before}."
        )
    return result
