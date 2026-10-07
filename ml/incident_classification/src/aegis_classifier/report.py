from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import load_json, resolve_model


def load_evaluation(model: str | Path, artifact_root: Path | None = None) -> dict[str, Any]:
    model_dir = resolve_model(model, artifact_root)
    return {
        "manifest": load_json(model_dir / "manifest.json"),
        "metrics": load_json(model_dir / "metrics.json"),
        "cv_results": load_json(model_dir / "cv_results.json"),
    }
