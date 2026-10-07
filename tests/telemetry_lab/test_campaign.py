from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.aegis_telemetry_lab.campaign import load_campaign_plan
from scripts.aegis_telemetry_lab.config import load_config
from scripts.aegis_telemetry_lab.errors import LabError
from scripts.aegis_telemetry_lab.scenarios import load_scenarios


class CampaignPlanTests(unittest.TestCase):
    def test_committed_plan_is_interleaved_and_matches_counts(self) -> None:
        config = load_config()
        scenarios = load_scenarios(config.scenarios_file)
        plan = load_campaign_plan(
            config.infrastructure_dir / "campaigns" / "anomaly-v1.json", scenarios
        )
        self.assertEqual(Counter(plan.order), Counter(plan.required_runs))
        self.assertEqual(plan.required_runs["normal"], 6)
        self.assertEqual(plan.timings.capture_seconds, 60)
        self.assertEqual(plan.restart_services["memory_leak"], ("email",))
        self.assertLess(max(len(list(group)) for group in _groups(plan.order)), 3)

    def test_plan_rejects_order_count_mismatch(self) -> None:
        config = load_config()
        scenarios = load_scenarios(config.scenarios_file)
        document = json.loads(
            (config.infrastructure_dir / "campaigns" / "anomaly-v1.json").read_text()
        )
        document["order"] = document["order"][:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(LabError, "do not match"):
                load_campaign_plan(path, scenarios)


def _groups(values: tuple[str, ...]):
    prior = object()
    group = []
    for value in values:
        if value != prior and group:
            yield group
            group = []
        group.append(value)
        prior = value
    if group:
        yield group
