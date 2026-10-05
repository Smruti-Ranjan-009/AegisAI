from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from scripts.aegis_telemetry_lab.config import LabConfig, Timings
from scripts.aegis_telemetry_lab.demo import DemoEnvironment


class DemoLifecycleTests(unittest.TestCase):
    def test_start_recreates_collector_after_clearing_idle_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = LabConfig(
                repo_root=Path(temporary_directory),
                otel_demo_version="3.1.0",
                git_ref="3.1.0",
                expected_commit="dedc0178918e260823323b8d95005a8cb924b007",
                repository_url="https://example.invalid/demo.git",
                compose_project="test",
                timings=Timings(0, 1, 0, 0),
                frontend_proxy_port=18080,
                envoy_admin_port=19000,
            )
            demo = DemoEnvironment(config)
            demo.setup = MagicMock(return_value=config.expected_commit)  # type: ignore[method-assign]
            demo.check_docker_daemon = MagicMock()  # type: ignore[method-assign]
            demo.clear_idle_capture = MagicMock()  # type: ignore[method-assign]
            demo.compose = MagicMock(return_value="")  # type: ignore[method-assign]
            demo.recreate_collector = MagicMock()  # type: ignore[method-assign]

            demo.start()

            demo.clear_idle_capture.assert_called_once_with()
            demo.recreate_collector.assert_called_once_with(config.idle_capture_dir)


if __name__ == "__main__":
    unittest.main()
