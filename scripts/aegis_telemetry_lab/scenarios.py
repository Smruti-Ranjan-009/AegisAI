from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import LabError


@dataclass(frozen=True)
class FeatureFlag:
    name: str
    variant: str
    baseline_variant: str


@dataclass(frozen=True)
class Scenario:
    name: str
    label: str
    description: str
    feature_flag: FeatureFlag | None
    expected_affected_services: tuple[str, ...]


def load_scenarios(path: Path) -> dict[str, Scenario]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"Cannot read scenario definitions {path}: {exc}") from exc

    if document.get("schema_version") != 1 or not isinstance(document.get("scenarios"), list):
        raise LabError("Scenario document must have schema_version 1 and a scenarios array.")

    scenarios: dict[str, Scenario] = {}
    for item in document["scenarios"]:
        if not isinstance(item, dict):
            raise LabError("Every scenario definition must be an object.")
        try:
            name = item["name"]
            label = item["label"]
            description = item["description"]
            affected = item["expected_affected_services"]
        except KeyError as exc:
            raise LabError(f"Scenario is missing required field {exc.args[0]!r}.") from exc
        if not all(isinstance(value, str) and value for value in (name, label, description)):
            raise LabError("Scenario name, label, and description must be non-empty strings.")
        if name in scenarios:
            raise LabError(f"Duplicate scenario name: {name}")
        if not isinstance(affected, list) or not all(isinstance(x, str) and x for x in affected):
            raise LabError(f"Scenario {name!r} has invalid expected_affected_services.")

        flag_data = item.get("feature_flag")
        feature_flag = None
        if flag_data is not None:
            if not isinstance(flag_data, dict):
                raise LabError(f"Scenario {name!r} feature_flag must be an object or null.")
            try:
                feature_flag = FeatureFlag(
                    name=flag_data["name"],
                    variant=flag_data["variant"],
                    baseline_variant=flag_data["baseline_variant"],
                )
            except KeyError as exc:
                raise LabError(
                    f"Scenario {name!r} feature_flag is missing {exc.args[0]!r}."
                ) from exc
            if not all(
                isinstance(value, str) and value
                for value in (
                    feature_flag.name,
                    feature_flag.variant,
                    feature_flag.baseline_variant,
                )
            ):
                raise LabError(f"Scenario {name!r} feature flag values must be strings.")

        scenarios[name] = Scenario(
            name=name,
            label=label,
            description=description,
            feature_flag=feature_flag,
            expected_affected_services=tuple(affected),
        )

    if "normal" not in scenarios or scenarios["normal"].feature_flag is not None:
        raise LabError("A normal scenario without a feature flag is required.")
    return scenarios


def get_scenario(scenarios: dict[str, Scenario], name: str) -> Scenario:
    try:
        return scenarios[name]
    except KeyError as exc:
        available = ", ".join(sorted(scenarios))
        raise LabError(f"Unknown scenario {name!r}. Available scenarios: {available}") from exc


def managed_baselines(scenarios: dict[str, Scenario]) -> dict[str, str]:
    baselines: dict[str, str] = {}
    for scenario in scenarios.values():
        flag = scenario.feature_flag
        if flag is None:
            continue
        previous = baselines.setdefault(flag.name, flag.baseline_variant)
        if previous != flag.baseline_variant:
            raise LabError(f"Conflicting baseline variants for feature flag {flag.name!r}.")
    return baselines


def validate_against_upstream(
    scenarios: dict[str, Scenario], flag_document: dict[str, object]
) -> None:
    upstream_flags = flag_document.get("flags")
    if not isinstance(upstream_flags, dict):
        raise LabError("Upstream flag document has no flags object.")
    for scenario in scenarios.values():
        flag = scenario.feature_flag
        if flag is None:
            continue
        upstream = upstream_flags.get(flag.name)
        if not isinstance(upstream, dict):
            raise LabError(
                f"Scenario {scenario.name!r} references missing upstream flag {flag.name!r}."
            )
        variants = upstream.get("variants")
        if not isinstance(variants, dict):
            raise LabError(f"Upstream flag {flag.name!r} has no variants object.")
        for variant in (flag.variant, flag.baseline_variant):
            if variant not in variants:
                raise LabError(
                    f"Scenario {scenario.name!r} references invalid variant {variant!r} "
                    f"for upstream flag {flag.name!r}."
                )
