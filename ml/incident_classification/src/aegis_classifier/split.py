from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .config import CLASS_NAMES, RANDOM_STATE, TEST_RUNS_PER_CLASS
from .errors import ClassificationError


def _hash_order(run_ids: list[str], scenario: str, seed: int) -> list[str]:
    return sorted(
        run_ids,
        key=lambda run_id: hashlib.sha256(
            f"phase6:{seed}:{scenario}:{run_id}".encode()
        ).hexdigest(),
    )


@dataclass(frozen=True)
class ClassificationSplit:
    development_run_ids: tuple[str, ...]
    test_run_ids: tuple[str, ...]
    random_state: int = RANDOM_STATE

    def validate(self, run_scenarios: dict[str, str]) -> None:
        development, test = set(self.development_run_ids), set(self.test_run_ids)
        if development & test:
            raise ClassificationError("Development/test run overlap detected.")
        if development | test != set(run_scenarios):
            raise ClassificationError("Classification split does not cover all runs exactly.")
        for scenario in CLASS_NAMES:
            development_count = sum(run_scenarios[item] == scenario for item in development)
            test_count = sum(run_scenarios[item] == scenario for item in test)
            if development_count < 4 or test_count != TEST_RUNS_PER_CLASS:
                raise ClassificationError(
                    f"Split requires >=4 development and 2 test runs for {scenario}; "
                    f"found {development_count} and {test_count}."
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "random_state": self.random_state,
            "development_run_ids": list(self.development_run_ids),
            "test_run_ids": list(self.test_run_ids),
        }


def build_frozen_split(
    run_scenarios: dict[str, str],
    preferred_test_run_ids: set[str] | None = None,
    seed: int = RANDOM_STATE,
) -> ClassificationSplit:
    preferred = preferred_test_run_ids or set()
    development: list[str] = []
    test: list[str] = []
    for scenario in CLASS_NAMES:
        candidates = [run_id for run_id, value in run_scenarios.items() if value == scenario]
        if len(candidates) < 6:
            raise ClassificationError(f"{scenario} requires at least 6 independent runs.")
        preferred_candidates = [run_id for run_id in candidates if run_id in preferred]
        pool = preferred_candidates if len(preferred_candidates) >= 2 else candidates
        selected = set(_hash_order(pool, scenario, seed)[:TEST_RUNS_PER_CLASS])
        test.extend(selected)
        development.extend(run_id for run_id in candidates if run_id not in selected)
    result = ClassificationSplit(tuple(sorted(development)), tuple(sorted(test)), seed)
    result.validate(run_scenarios)
    return result
