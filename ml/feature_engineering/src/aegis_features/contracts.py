from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parents[2] / "feature_catalog_v1.json"


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def metadata_columns(dataset: str = "service_windows") -> tuple[str, ...]:
    return tuple(load_catalog()[dataset]["metadata_columns"])


def target_columns(dataset: str = "service_windows") -> tuple[str, ...]:
    return tuple(load_catalog()[dataset]["target_columns"])


def feature_columns(dataset: str = "service_windows") -> tuple[str, ...]:
    return tuple(load_catalog()[dataset]["feature_columns"])


def ordered_columns(dataset: str) -> tuple[str, ...]:
    return metadata_columns(dataset) + target_columns(dataset) + feature_columns(dataset)
