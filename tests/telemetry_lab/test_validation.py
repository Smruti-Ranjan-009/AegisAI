from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.aegis_telemetry_lab.errors import LabError
from scripts.aegis_telemetry_lab.validation import (
    resolve_run_directory,
    validate_capture,
    validate_jsonl,
    validate_manifest,
)


def otlp_batch(root_key: str, service: str = "frontend") -> dict[str, object]:
    return {
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


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.raw_root = Path(self.temporary_directory.name) / "raw"
        self.raw_root.mkdir()
        self.run_id = "20261005T153012Z-normal-a1b2c3"
        self.run_dir = self.raw_root / self.run_id
        self.run_dir.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_complete_run(self) -> None:
        roots = {
            "metrics.jsonl": "resourceMetrics",
            "logs.jsonl": "resourceLogs",
            "traces.jsonl": "resourceSpans",
        }
        for filename, root_key in roots.items():
            (self.run_dir / filename).write_text(
                json.dumps(otlp_batch(root_key)) + "\n", encoding="utf-8"
            )
        manifest = {
            "schema_version": 1,
            "run_id": self.run_id,
            "scenario": "normal",
            "label": "normal",
            "started_at_utc": "2026-10-05T15:30:12Z",
            "ended_at_utc": "2026-10-05T15:31:12Z",
            "duration_seconds": 60,
            "otel_demo_version": "3.1.0",
            "upstream_git_commit": "dedc0178918e260823323b8d95005a8cb924b007",
            "feature_flag": None,
            "expected_affected_services": [],
            "signals": {
                "metrics": "metrics.jsonl",
                "logs": "logs.jsonl",
                "traces": "traces.jsonl",
            },
        }
        (self.run_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_jsonl_and_service_identity_validation(self) -> None:
        path = self.run_dir / "traces.jsonl"
        path.write_text(
            json.dumps(otlp_batch("resourceSpans", "checkout")) + "\n", encoding="utf-8"
        )

        result = validate_jsonl(path, "resourceSpans")

        self.assertEqual(result.batches, 1)
        self.assertEqual(result.services, ("checkout",))

    def test_invalid_jsonl_is_rejected(self) -> None:
        path = self.run_dir / "logs.jsonl"
        path.write_text("not-json\n", encoding="utf-8")

        with self.assertRaisesRegex(LabError, "Invalid JSON"):
            validate_jsonl(path, "resourceLogs")

    def test_wrong_signal_type_is_rejected(self) -> None:
        path = self.run_dir / "metrics.jsonl"
        path.write_text(json.dumps(otlp_batch("resourceSpans")) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(LabError, "Unexpected OTLP structure"):
            validate_jsonl(path, "resourceMetrics")

    def test_manifest_validation_and_complete_capture(self) -> None:
        self._write_complete_run()

        manifest = validate_manifest(self.run_dir / "manifest.json")
        result = validate_capture(self.run_dir)

        self.assertEqual(manifest["run_id"], self.run_id)
        self.assertEqual(result.services, ("frontend",))

    def test_manifest_missing_required_field_is_rejected(self) -> None:
        (self.run_dir / "manifest.json").write_text(
            json.dumps({"schema_version": 1}), encoding="utf-8"
        )

        with self.assertRaisesRegex(LabError, "missing required fields"):
            validate_manifest(self.run_dir / "manifest.json")

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaisesRegex(LabError, "Unsafe or invalid run ID"):
            resolve_run_directory(self.raw_root, "../outside")


if __name__ == "__main__":
    unittest.main()
