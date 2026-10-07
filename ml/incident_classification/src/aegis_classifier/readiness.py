from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .config import CLASS_NAMES, FROZEN_ANOMALY_MODEL_ID, MIN_RUNS_PER_CLASS, repository_root
from .dataset import ClassificationDataset


def check_readiness(
    dataset: ClassificationDataset,
    *,
    raw_root: Path | None = None,
    anomaly_artifact_root: Path | None = None,
) -> dict[str, Any]:
    rows = dataset.table.to_pylist()
    errors: list[str] = []
    counts = Counter(row["scenario"] for row in rows)
    if set(counts) != set(CLASS_NAMES):
        errors.append("Target vocabulary is not exactly the five supported fault classes.")
    for scenario in CLASS_NAMES:
        if counts[scenario] < MIN_RUNS_PER_CLASS:
            errors.append(
                f"{scenario} requires {MIN_RUNS_PER_CLASS} runs; found {counts[scenario]}."
            )
    run_ids = [row["run_id"] for row in rows]
    if len(run_ids) != len(set(run_ids)):
        errors.append("Duplicate run IDs are not allowed.")
    feature_names = tuple(dataset.manifest["feature_names"])
    matrix = np.asarray([[row[name] for name in feature_names] for row in rows], dtype=float)
    if not np.all(np.isfinite(matrix)):
        errors.append("Classification predictive features contain non-finite values.")
    if dataset.manifest.get("upstream_anomaly_model_id") != FROZEN_ANOMALY_MODEL_ID:
        errors.append("Classification dataset references the wrong Phase 5 model ID.")
    artifact_root = anomaly_artifact_root or repository_root() / "artifacts" / "anomaly_detection"
    manifest_path = artifact_root / FROZEN_ANOMALY_MODEL_ID / "manifest.json"
    try:
        anomaly_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Frozen Phase 5 artifact is unavailable: {exc}")
    else:
        if anomaly_manifest.get("model_id") != FROZEN_ANOMALY_MODEL_ID:
            errors.append("Frozen Phase 5 artifact manifest has the wrong model ID.")

    root = raw_root or repository_root() / "data" / "raw"
    durations: set[int] = set()
    for row in rows:
        run_id, scenario = row["run_id"], row["scenario"]
        try:
            manifest = json.loads((root / run_id / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{run_id}: failed capture manifest: {exc}")
            continue
        if manifest.get("run_id") != run_id or manifest.get("scenario") != scenario:
            errors.append(f"{run_id}: capture identity/scenario mismatch.")
        if manifest.get("validation_status") not in (None, "PASS"):
            errors.append(f"{run_id}: capture validation did not pass.")
        feature_flag = manifest.get("feature_flag")
        if not isinstance(feature_flag, dict) or feature_flag.get("restored") is not True:
            errors.append(f"{run_id}: fault flag restoration is not recorded.")
        duration = manifest.get("duration_seconds")
        if isinstance(duration, int):
            durations.add(duration)
        for filename in ("metrics.jsonl", "logs.jsonl", "traces.jsonl"):
            signal = root / run_id / filename
            if not signal.is_file() or signal.stat().st_size == 0:
                errors.append(f"{run_id}: missing or empty {filename}.")
    if durations != {60}:
        errors.append(f"Capture durations must be exactly 60 seconds; found {sorted(durations)}.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "dataset_id": dataset.dataset_id,
        "row_count": len(rows),
        "feature_count": len(feature_names),
        "class_counts": {name: counts[name] for name in CLASS_NAMES},
        "capture_durations_seconds": sorted(durations),
        "upstream_anomaly_model_id": dataset.manifest.get("upstream_anomaly_model_id"),
        "development_rows": len(dataset.split.development_run_ids),
        "test_rows": len(dataset.split.test_run_ids),
        "errors": errors,
    }
