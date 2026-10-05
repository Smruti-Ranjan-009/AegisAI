from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.aegis_telemetry_lab.capture import generate_run_id, run_capture
from scripts.aegis_telemetry_lab.config import LabConfig, Timings
from scripts.aegis_telemetry_lab.flags import current_variant
from scripts.aegis_telemetry_lab.scenarios import FeatureFlag, Scenario


def write_signal(path: Path, root_key: str, service: str) -> None:
    batch = {
        root_key: [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service}}
                    ]
                }
            }
        ]
    }
    path.write_text(json.dumps(batch) + "\n", encoding="utf-8")


class FakeDemo:
    def __init__(self, config: LabConfig) -> None:
        self.config = config
        self.restored_idle = False

    def ensure_started(self) -> None:
        return None

    def verify_checkout(self) -> str:
        return self.config.expected_commit

    def verify_scenarios(self, scenarios: dict[str, Scenario]) -> None:
        return None

    def verify_flag(self, flag_name: str, expected_variant: str) -> None:
        if current_variant(self.config.runtime_flag_file, flag_name) != expected_variant:
            raise AssertionError("flag variant was not applied")

    def verify_traffic(self) -> tuple[str, ...]:
        return ("frontend", "load-generator")

    def recreate_collector(self, capture_dir: Path) -> None:
        write_signal(capture_dir / "metrics.jsonl", "resourceMetrics", "ad")
        write_signal(capture_dir / "logs.jsonl", "resourceLogs", "ad")
        write_signal(capture_dir / "traces.jsonl", "resourceSpans", "ad")

    def stop_collector(self, capture_dir: Path) -> None:
        return None

    def restore_idle_collector(self) -> None:
        self.restored_idle = True


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.config = LabConfig(
            repo_root=root,
            otel_demo_version="3.1.0",
            git_ref="3.1.0",
            expected_commit="dedc0178918e260823323b8d95005a8cb924b007",
            repository_url="https://example.invalid/demo.git",
            compose_project="test",
            timings=Timings(0, 1, 0, 0),
            frontend_proxy_port=18080,
            envoy_admin_port=19000,
        )
        self.config.runtime_flag_dir.mkdir(parents=True)
        self.config.raw_data_dir.mkdir(parents=True)
        self.config.runtime_flag_file.write_text(
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
        self.scenarios = {
            "normal": Scenario("normal", "normal", "Baseline", None, ()),
            "cpu_saturation": Scenario(
                "cpu_saturation",
                "cpu_saturation",
                "CPU fault",
                FeatureFlag("adHighCpu", "on", "off"),
                ("ad",),
            ),
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_unique_run_id_generation_skips_collision(self) -> None:
        def fixed_time() -> datetime:
            return datetime(2026, 10, 5, 15, 30, 12, tzinfo=UTC)

        (self.config.raw_data_dir / "20261005T153012Z-normal-a1b2c3").mkdir()
        tokens = iter(("a1b2c3", "d4e5f6"))

        run_id = generate_run_id(
            self.config.raw_data_dir,
            "normal",
            now=fixed_time,
            token_hex=lambda _: next(tokens),
        )

        self.assertEqual(run_id, "20261005T153012Z-normal-d4e5f6")

    def test_run_creates_manifest_and_restores_fault(self) -> None:
        fake_demo = FakeDemo(self.config)

        def fixed_time() -> datetime:
            return datetime(2026, 10, 5, 15, 30, 12, tzinfo=UTC)

        result = run_capture(
            self.config,
            fake_demo,  # type: ignore[arg-type]
            self.scenarios,
            self.scenarios["cpu_saturation"],
            Timings(0, 1, 0, 0),
            sleeper=lambda _: None,
            now=fixed_time,
        )

        manifest = json.loads(
            (self.config.raw_data_dir / result.run_id / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["feature_flag"]["name"], "adHighCpu")
        self.assertTrue(manifest["feature_flag"]["restored"])
        self.assertEqual(current_variant(self.config.runtime_flag_file, "adHighCpu"), "off")
        self.assertTrue(fake_demo.restored_idle)


if __name__ == "__main__":
    unittest.main()
