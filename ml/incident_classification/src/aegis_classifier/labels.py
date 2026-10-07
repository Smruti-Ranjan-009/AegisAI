from __future__ import annotations

import json
from pathlib import Path

from .config import CLASS_NAMES, repository_root
from .errors import ClassificationError


def validate_class_vocabulary(path: Path | None = None) -> tuple[str, ...]:
    scenario_path = path or (
        repository_root() / "infrastructure" / "telemetry-lab" / "scenarios.json"
    )
    try:
        document = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"Cannot read scenario configuration: {exc}") from exc
    entries = document.get("scenarios") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise ClassificationError("Scenario configuration requires a scenarios array.")
    labels = {
        item.get("name")
        for item in entries
        if isinstance(item, dict) and item.get("name") != "normal"
    }
    if labels != set(CLASS_NAMES):
        raise ClassificationError(
            "Classifier vocabulary must exactly match the five configured fault scenarios."
        )
    return CLASS_NAMES
