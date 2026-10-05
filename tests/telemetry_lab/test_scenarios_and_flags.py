from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.aegis_telemetry_lab.errors import LabError
from scripts.aegis_telemetry_lab.flags import current_variant, patch_variants, temporary_patch
from scripts.aegis_telemetry_lab.scenarios import (
    get_scenario,
    load_scenarios,
    validate_against_upstream,
)


class ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_scenarios(self, scenarios: list[dict[str, object]]) -> Path:
        path = self.root / "scenarios.json"
        path.write_text(
            json.dumps({"schema_version": 1, "scenarios": scenarios}), encoding="utf-8"
        )
        return path

    def test_scenario_parsing_and_upstream_validation(self) -> None:
        path = self._write_scenarios(
            [
                {
                    "name": "normal",
                    "label": "normal",
                    "description": "Baseline",
                    "feature_flag": None,
                    "expected_affected_services": [],
                },
                {
                    "name": "cpu_saturation",
                    "label": "cpu_saturation",
                    "description": "CPU fault",
                    "feature_flag": {
                        "name": "adHighCpu",
                        "variant": "on",
                        "baseline_variant": "off",
                    },
                    "expected_affected_services": ["ad"],
                },
            ]
        )
        scenarios = load_scenarios(path)
        validate_against_upstream(
            scenarios,
            {"flags": {"adHighCpu": {"variants": {"off": False, "on": True}}}},
        )

        self.assertEqual(scenarios["cpu_saturation"].feature_flag.name, "adHighCpu")

    def test_invalid_scenario_is_rejected(self) -> None:
        path = self._write_scenarios(
            [
                {
                    "name": "normal",
                    "label": "normal",
                    "description": "Baseline",
                    "feature_flag": None,
                    "expected_affected_services": [],
                }
            ]
        )
        scenarios = load_scenarios(path)

        with self.assertRaisesRegex(LabError, "Unknown scenario"):
            get_scenario(scenarios, "invented-fault")

    def test_unknown_upstream_variant_is_rejected(self) -> None:
        path = self._write_scenarios(
            [
                {
                    "name": "normal",
                    "label": "normal",
                    "description": "Baseline",
                    "feature_flag": None,
                    "expected_affected_services": [],
                },
                {
                    "name": "fault",
                    "label": "fault",
                    "description": "Fault",
                    "feature_flag": {
                        "name": "realFlag",
                        "variant": "fabricated",
                        "baseline_variant": "off",
                    },
                    "expected_affected_services": ["service"],
                },
            ]
        )

        with self.assertRaisesRegex(LabError, "invalid variant"):
            validate_against_upstream(
                load_scenarios(path),
                {"flags": {"realFlag": {"variants": {"off": False, "on": True}}}},
            )


class FeatureFlagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "demo.flagd.json"
        self.path.write_text(
            json.dumps(
                {
                    "flags": {
                        "adHighCpu": {
                            "defaultVariant": "off",
                            "variants": {"off": False, "on": True},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_feature_flag_patching(self) -> None:
        patch_variants(self.path, {"adHighCpu": "on"})

        self.assertEqual(current_variant(self.path, "adHighCpu"), "on")

    def test_feature_flag_is_restored_after_simulated_failure(self) -> None:
        original = self.path.read_bytes()

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            with temporary_patch(self.path, {"adHighCpu": "on"}):
                self.assertEqual(current_variant(self.path, "adHighCpu"), "on")
                raise RuntimeError("simulated capture failure")

        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(current_variant(self.path, "adHighCpu"), "off")


if __name__ == "__main__":
    unittest.main()
