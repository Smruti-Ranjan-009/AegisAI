from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import repository_root
from .errors import AnomalyError


@dataclass(frozen=True)
class ScenarioGroundTruth:
    expected_services: dict[str, frozenset[str]]

    def annotate(self, row: dict[str, Any]) -> dict[str, Any]:
        scenario = str(row["scenario"])
        if scenario not in self.expected_services:
            raise AnomalyError(f"Dataset row has unknown scenario {scenario!r}.")
        result = dict(row)
        result["run_has_fault"] = scenario != "normal"
        result["is_injected_fault_service"] = (
            scenario != "normal" and str(row["service_name"]) in self.expected_services[scenario]
        )
        result["expected_affected_services"] = sorted(self.expected_services[scenario])
        if scenario == "normal":
            result["ground_truth_role"] = "normal_negative"
        elif result["is_injected_fault_service"]:
            result["ground_truth_role"] = "injected_positive"
        else:
            result["ground_truth_role"] = "propagation_ambiguous"
        return result


def load_ground_truth(path: Path | None = None) -> ScenarioGroundTruth:
    scenario_path = path or (
        repository_root() / "infrastructure" / "telemetry-lab" / "scenarios.json"
    )
    try:
        document = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnomalyError(f"Cannot read scenario configuration {scenario_path}: {exc}") from exc
    scenarios = document.get("scenarios") if isinstance(document, dict) else None
    if not isinstance(scenarios, list):
        raise AnomalyError("Scenario configuration requires a scenarios array.")
    expected: dict[str, frozenset[str]] = {}
    for item in scenarios:
        if not isinstance(item, dict):
            raise AnomalyError("Scenario entries must be objects.")
        name = item.get("name")
        services = item.get("expected_affected_services")
        if not isinstance(name, str) or not isinstance(services, list) or not all(
            isinstance(service, str) for service in services
        ):
            raise AnomalyError("Scenario name/expected_affected_services is invalid.")
        expected[name] = frozenset(services)
    if expected.get("normal") != frozenset():
        raise AnomalyError("Normal scenario must have no expected affected services.")
    return ScenarioGroundTruth(expected)
