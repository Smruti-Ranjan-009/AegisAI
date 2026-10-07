from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .config import FAULT_SCENARIOS, RANDOM_STATE
from .errors import AnomalyError


@dataclass(frozen=True)
class RunSplit:
    training_run_ids: tuple[str, ...]
    validation_run_ids: tuple[str, ...]
    test_run_ids: tuple[str, ...]
    random_state: int = RANDOM_STATE

    def validate(self, run_scenarios: dict[str, str]) -> None:
        train, validation, test = map(
            set, (self.training_run_ids, self.validation_run_ids, self.test_run_ids)
        )
        if train & validation or train & test or validation & test:
            raise AnomalyError("Run split overlap detected.")
        if train | validation | test != set(run_scenarios):
            raise AnomalyError("Run split does not cover the source runs exactly.")
        if any(run_scenarios[run_id] != "normal" for run_id in train):
            raise AnomalyError("Training split contains a fault run.")
        for scenario in FAULT_SCENARIOS:
            if not any(run_scenarios[run_id] == scenario for run_id in validation):
                raise AnomalyError(f"Validation split has no {scenario} run.")
            if not any(run_scenarios[run_id] == scenario for run_id in test):
                raise AnomalyError(f"Test split has no {scenario} run.")
        if not any(run_scenarios[run_id] == "normal" for run_id in validation):
            raise AnomalyError("Validation split has no normal run.")
        if not any(run_scenarios[run_id] == "normal" for run_id in test):
            raise AnomalyError("Test split has no normal run.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "random_state": self.random_state,
            "training_run_ids": list(self.training_run_ids),
            "validation_run_ids": list(self.validation_run_ids),
            "test_run_ids": list(self.test_run_ids),
        }


def _ordered(run_ids: list[str], scenario: str, seed: int) -> list[str]:
    return sorted(
        run_ids,
        key=lambda run_id: hashlib.sha256(
            f"{seed}:{scenario}:{run_id}".encode()
        ).hexdigest(),
    )


def build_run_split(run_scenarios: dict[str, str], seed: int = RANDOM_STATE) -> RunSplit:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for run_id, scenario in run_scenarios.items():
        grouped[scenario].append(run_id)
    normal = _ordered(grouped["normal"], "normal", seed)
    if len(normal) < 3:
        raise AnomalyError("At least three normal runs are required for train/validation/test.")
    validation = [normal[0]]
    test = [normal[1]]
    training = normal[2:]
    for scenario in FAULT_SCENARIOS:
        fault = _ordered(grouped[scenario], scenario, seed)
        if len(fault) < 2:
            raise AnomalyError(f"At least two {scenario} runs are required.")
        validation.extend(fault[::2])
        test.extend(fault[1::2])
    split = RunSplit(
        tuple(sorted(training)),
        tuple(sorted(validation)),
        tuple(sorted(test)),
        seed,
    )
    split.validate(run_scenarios)
    return split
