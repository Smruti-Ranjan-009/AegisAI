from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from aegis_anomaly.data import load_feature_dataset

from .anomaly_adapter import FrozenAnomalyAdapter
from .artifacts import load_bundle, resolve_model
from .dataset import build_classification_dataset, load_classification_dataset
from .errors import ClassificationError
from .readiness import check_readiness
from .report import load_evaluation
from .training import matrix_for_runs, train


def _print(document: dict[str, Any]) -> None:
    print(json.dumps(document, indent=2, sort_keys=True, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="aegis-classifier")
    root.add_argument("--feature-root", type=Path, default=Path("data/features"))
    root.add_argument(
        "--classification-root", type=Path, default=Path("data/classification")
    )
    root.add_argument(
        "--anomaly-artifact-root", type=Path, default=Path("artifacts/anomaly_detection")
    )
    root.add_argument(
        "--artifact-root", type=Path, default=Path("artifacts/incident_classification")
    )
    commands = root.add_subparsers(dest="command", required=True)
    anomaly = commands.add_parser("anomaly-score", help="Verify frozen Phase 5 scoring")
    anomaly.add_argument("--feature-dataset", required=True)
    build = commands.add_parser("build", help="Build the one-row-per-run dataset")
    build.add_argument("--feature-dataset", required=True)
    build.add_argument(
        "--campaign-result",
        type=Path,
        default=Path(".runtime/telemetry-lab/campaigns/classification-v1-result.json"),
    )
    readiness = commands.add_parser("readiness", help="Check the Phase 6 data gate")
    readiness.add_argument("--dataset", required=True)
    training = commands.add_parser("train", help="CV, select, fit, evaluate, and persist")
    training.add_argument("--dataset", required=True)
    evaluation = commands.add_parser("evaluate", help="Read persisted final evaluation")
    evaluation.add_argument("--model", required=True)
    scoring = commands.add_parser("score", help="Score a classification dataset offline")
    scoring.add_argument("--model", required=True)
    scoring.add_argument("--dataset", required=True)
    return root


def execute(arguments: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    if arguments.command == "anomaly-score":
        dataset = load_feature_dataset(arguments.feature_dataset, arguments.feature_root)
        adapter = FrozenAnomalyAdapter(artifact_root=arguments.anomaly_artifact_root)
        rows = adapter.score(dataset)
        scores = np.asarray([row.anomaly_score for row in rows])
        return {
            "upstream_anomaly_model_id": adapter.model_id,
            "feature_dataset_id": dataset.dataset_id,
            "rows_scored": len(rows),
            "threshold": adapter.threshold,
            "anomaly_decisions": int(sum(row.anomaly_decision for row in rows)),
            "score_min": float(scores.min()),
            "score_max": float(scores.max()),
            "excluded_services": adapter.manifest["excluded_services"],
        }, True
    if arguments.command == "build":
        result = build_classification_dataset(
            arguments.feature_dataset,
            anomaly_artifact_root=arguments.anomaly_artifact_root,
            feature_root=arguments.feature_root,
            output_root=arguments.classification_root,
            campaign_result=arguments.campaign_result,
        )
        return {
            "dataset_id": result.dataset_id,
            "path": str(result.path),
            "row_count": result.table.num_rows,
            "feature_count": len(result.manifest["feature_names"]),
            "scenario_counts": result.manifest["scenario_counts"],
            "split": result.split.as_dict(),
            "quality": result.quality,
        }, True
    if arguments.command == "readiness":
        dataset = load_classification_dataset(arguments.dataset, arguments.classification_root)
        result = check_readiness(dataset, anomaly_artifact_root=arguments.anomaly_artifact_root)
        return result, result["status"] == "PASS"
    if arguments.command == "train":
        dataset = load_classification_dataset(arguments.dataset, arguments.classification_root)
        result = train(
            dataset,
            output_root=arguments.artifact_root,
            anomaly_artifact_root=arguments.anomaly_artifact_root,
        )
        return {
            "model_id": result["model_id"],
            "model_dir": result["model_dir"],
            "selected_model": result["selected_model"],
            "reload_verified": result["reload_verified"],
            "final_test": result["metrics"]["final_test"],
            "performance": result["metrics"]["performance"],
        }, True
    if arguments.command == "evaluate":
        return load_evaluation(arguments.model, arguments.artifact_root), True

    dataset = load_classification_dataset(arguments.dataset, arguments.classification_root)
    model_dir = resolve_model(arguments.model, arguments.artifact_root)
    bundle = load_bundle(model_dir / "model.joblib")
    values, labels, run_ids = matrix_for_runs(dataset, set(dataset.manifest["source_run_ids"]))
    started = time.perf_counter()
    probabilities = bundle.predict_probabilities(values)
    predictions = bundle.predict(values)
    elapsed = time.perf_counter() - started
    rows = []
    for index, run_id in enumerate(run_ids):
        ranking = np.argsort(probabilities[index])[::-1]
        rows.append(
            {
                "run_id": run_id,
                "actual_class": str(labels[index]),
                "predicted_class": str(predictions[index]),
                "top_probability": float(probabilities[index, ranking[0]]),
                "second_probability": float(probabilities[index, ranking[1]]),
                "probability_by_class": {
                    name: float(probabilities[index, position])
                    for position, name in enumerate(bundle.class_names)
                },
            }
        )
    return {
        "model_id": bundle.model_id,
        "dataset_id": dataset.dataset_id,
        "row_count": len(rows),
        "scoring_duration_seconds": elapsed,
        "runs_per_second": len(rows) / elapsed if elapsed else None,
        "predictions": rows,
    }, True


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        result, success = execute(arguments)
        _print(result)
        return 0 if success else 2
    except (ClassificationError, ValueError) as exc:
        print(f"aegis-classifier: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
