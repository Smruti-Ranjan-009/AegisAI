from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import EXCLUDED_SERVICES, FAULT_SCENARIOS, ReadinessRequirements
from .data import FeatureDataset
from .labels import load_ground_truth


def _raw_manifest_status(
    raw_root: Path,
    run_id: str,
    expected_scenario: str,
    expected_services: frozenset[str],
) -> str | None:
    path = raw_root / run_id / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"{run_id}: raw manifest unavailable: {exc}"
    if manifest.get("run_id") != run_id or manifest.get("scenario") != expected_scenario:
        return f"{run_id}: raw manifest identity/scenario mismatch"
    if manifest.get("validation_status") not in (None, "PASS"):
        return f"{run_id}: raw manifest validation_status is not PASS"
    feature_flag = manifest.get("feature_flag")
    if expected_scenario == "normal" and feature_flag is not None:
        return f"{run_id}: normal run unexpectedly has a feature flag"
    if expected_scenario != "normal" and (
        not isinstance(feature_flag, dict) or feature_flag.get("restored") is not True
    ):
        return f"{run_id}: fault feature flag was not recorded as restored"
    observed_expected = manifest.get("expected_affected_services")
    if set(observed_expected or []) != set(expected_services):
        return f"{run_id}: expected affected services differ from scenario configuration"
    for filename in ("metrics.jsonl", "logs.jsonl", "traces.jsonl"):
        signal = path.parent / filename
        if not signal.is_file() or signal.stat().st_size == 0:
            return f"{run_id}: required signal file is missing or empty: {filename}"
    return None


def check_readiness(
    dataset: FeatureDataset,
    *,
    requirements: ReadinessRequirements | None = None,
    raw_root: Path | None = None,
    excluded_services: frozenset[str] = EXCLUDED_SERVICES,
) -> dict[str, Any]:
    requirements = requirements or ReadinessRequirements()
    service_rows = dataset.service_windows.to_pylist()
    run_scenarios: dict[str, str] = {}
    errors: list[str] = []
    for row in service_rows:
        run_id, scenario = str(row["run_id"]), str(row["scenario"])
        prior = run_scenarios.setdefault(run_id, scenario)
        if prior != scenario:
            errors.append(f"{run_id}: appears with multiple scenarios")
    manifest_runs = set(dataset.manifest.get("source_run_ids", []))
    if manifest_runs != set(run_scenarios):
        errors.append("Feature manifest source_run_ids do not match service-window runs")

    counts = Counter(run_scenarios.values())
    if counts["normal"] < requirements.normal_runs:
        errors.append(
            f"normal requires {requirements.normal_runs} runs; found {counts['normal']}"
        )
    for scenario in FAULT_SCENARIOS:
        if counts[scenario] < requirements.fault_runs_per_scenario:
            errors.append(
                f"{scenario} requires {requirements.fault_runs_per_scenario} runs; "
                f"found {counts[scenario]}"
            )

    eligible_services = sorted(
        {str(row["service_name"]) for row in service_rows} - set(excluded_services)
    )
    excluded_observed = sorted(
        {str(row["service_name"]) for row in service_rows} & set(excluded_services)
    )
    normal_windows = sum(
        row["scenario"] == "normal" and row["service_name"] in eligible_services
        for row in service_rows
    )
    if normal_windows < requirements.normal_service_windows:
        errors.append(
            "eligible normal service windows require "
            f"{requirements.normal_service_windows}; found {normal_windows}"
        )

    root = raw_root or dataset.path.parent.parent / "raw"
    ground_truth = load_ground_truth()
    durations: set[int] = set()
    for run_id, scenario in sorted(run_scenarios.items()):
        issue = _raw_manifest_status(
            root,
            run_id,
            scenario,
            ground_truth.expected_services.get(scenario, frozenset()),
        )
        if issue:
            errors.append(issue)
            continue
        manifest = json.loads((root / run_id / "manifest.json").read_text(encoding="utf-8"))
        duration = manifest.get("duration_seconds")
        if isinstance(duration, int):
            durations.add(duration)
    if len(durations) > 1:
        errors.append(f"source captures mix incompatible durations: {sorted(durations)}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "dataset_id": dataset.dataset_id,
        "run_counts": dict(sorted(counts.items())),
        "total_runs": len(run_scenarios),
        "normal_service_window_count": normal_windows,
        "eligible_services": eligible_services,
        "excluded_services": excluded_observed,
        "capture_durations_seconds": sorted(durations),
        "requirements": {
            "normal_runs": requirements.normal_runs,
            "fault_runs_per_scenario": requirements.fault_runs_per_scenario,
            "normal_service_windows": requirements.normal_service_windows,
        },
        "errors": errors,
    }
