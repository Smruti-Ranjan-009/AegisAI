from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .artifacts import load_bundle, resolve_model
from .data import load_feature_dataset
from .errors import AnomalyError
from .labels import load_ground_truth
from .readiness import check_readiness
from .report import load_evaluation
from .robust_detector import RobustZScoreDetector
from .training import train


def _print(document: dict[str, Any]) -> None:
    print(json.dumps(document, indent=2, sort_keys=True, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="aegis-anomaly")
    root.add_argument("--feature-root", type=Path, default=Path("data/features"))
    root.add_argument(
        "--artifact-root", type=Path, default=Path("artifacts/anomaly_detection")
    )
    commands = root.add_subparsers(dest="command", required=True)
    readiness = commands.add_parser("readiness", help="Check the hard Phase 5 data gate")
    readiness.add_argument("--dataset", required=True)
    training = commands.add_parser("train", help="Train, select, evaluate, and persist a detector")
    training.add_argument("--dataset", required=True)
    evaluation = commands.add_parser("evaluate", help="Read a persisted final evaluation")
    evaluation.add_argument("--model", required=True)
    scoring = commands.add_parser("score", help="Score a Phase 4 feature dataset offline")
    scoring.add_argument("--model", required=True)
    scoring.add_argument("--dataset", required=True)
    return root


def execute(arguments: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    if arguments.command == "readiness":
        dataset = load_feature_dataset(arguments.dataset, arguments.feature_root)
        result = check_readiness(dataset)
        return result, result["status"] == "PASS"
    if arguments.command == "train":
        dataset = load_feature_dataset(arguments.dataset, arguments.feature_root)
        result = train(
            dataset,
            load_ground_truth(),
            output_root=arguments.artifact_root,
        )
        return {
            "model_id": result["model_id"],
            "model_dir": result["model_dir"],
            "selected_detector": result["selected_detector"],
            "threshold": result["threshold"],
            "reload_verified": result["reload_verified"],
            "test": result["metrics"]["test"],
            "performance": result["metrics"]["performance"],
        }, True
    if arguments.command == "evaluate":
        return load_evaluation(arguments.model, arguments.artifact_root), True

    dataset = load_feature_dataset(arguments.dataset, arguments.feature_root)
    model_dir = resolve_model(arguments.model, arguments.artifact_root)
    bundle = load_bundle(model_dir / "model.joblib")
    started = time.perf_counter()
    matrix, scores = bundle.matrix_and_scores(dataset, load_ground_truth())
    elapsed = time.perf_counter() - started
    decisions = scores > bundle.threshold
    highest = np.argsort(scores)[::-1][: min(10, len(scores))]
    result: dict[str, Any] = {
        "model_id": bundle.model_id,
        "dataset_id": dataset.dataset_id,
        "row_count": matrix.row_count,
        "anomaly_count": int(np.sum(decisions)),
        "threshold": bundle.threshold,
        "scoring_duration_seconds": elapsed,
        "rows_per_second": matrix.row_count / elapsed if elapsed else None,
        "latency_ms_per_row": elapsed * 1000 / matrix.row_count if matrix.row_count else None,
        "highest_scoring_rows": [
            {
                "run_id": matrix.metadata[index]["run_id"],
                "service_name": matrix.metadata[index]["service_name"],
                "scenario": matrix.metadata[index]["scenario"],
                "score": float(scores[index]),
                "is_anomaly": bool(decisions[index]),
            }
            for index in highest
        ],
    }
    if isinstance(bundle.detector, RobustZScoreDetector) and len(highest):
        transformed = bundle.imputer.transform(matrix.values[highest])
        result["top_contributors"] = bundle.detector.top_contributors(
            transformed, bundle.feature_names
        )
    return result, True


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = parser()
    arguments = argument_parser.parse_args(argv)
    try:
        result, success = execute(arguments)
        _print(result)
        return 0 if success else 2
    except (AnomalyError, ValueError) as exc:
        print(f"aegis-anomaly: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
