from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from .errors import AnomalyError


def _auc(y_true: np.ndarray, scores: np.ndarray, kind: str) -> float | None:
    if len(np.unique(y_true)) < 2:
        return None
    if kind == "roc":
        return float(roc_auc_score(y_true, scores))
    return float(average_precision_score(y_true, scores))


def binary_metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    if len(y_true) != len(scores) or len(y_true) == 0:
        raise AnomalyError("Evaluation requires aligned non-empty labels and scores.")
    predictions = scores > threshold
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[False, True]).ravel()
    negative_count = tn + fp
    return {
        "row_count": len(y_true),
        "roc_auc": _auc(y_true, scores, "roc"),
        "pr_auc": _auc(y_true, scores, "pr"),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "normal_fpr": float(fp / negative_count) if negative_count else None,
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }


def service_level_metrics(
    metadata: tuple[dict[str, Any], ...], scores: np.ndarray, threshold: float
) -> dict[str, Any]:
    selected = [
        index
        for index, item in enumerate(metadata)
        if item["ground_truth_role"] in {"normal_negative", "injected_positive"}
    ]
    labels = np.asarray(
        [metadata[index]["is_injected_fault_service"] for index in selected], dtype=bool
    )
    metrics = binary_metrics(labels, scores[selected], threshold)
    metrics["ambiguous_rows_excluded"] = len(metadata) - len(selected)
    return metrics


def run_level_metrics(
    metadata: tuple[dict[str, Any], ...], scores: np.ndarray, threshold: float
) -> dict[str, Any]:
    grouped: defaultdict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(metadata):
        grouped[item["run_id"]].append(index)
    run_ids = sorted(grouped)
    run_scores = np.asarray([float(np.max(scores[grouped[run_id]])) for run_id in run_ids])
    labels = np.asarray([metadata[grouped[run_id][0]]["run_has_fault"] for run_id in run_ids])
    metrics = binary_metrics(labels, run_scores, threshold)
    decisions = run_scores > threshold
    metrics.update(
        {
            "fault_runs_detected": int(np.sum(decisions & labels)),
            "fault_run_count": int(np.sum(labels)),
            "normal_runs_falsely_detected": int(np.sum(decisions & ~labels)),
            "normal_run_count": int(np.sum(~labels)),
            "scores": [
                {
                    "run_id": run_id,
                    "run_has_fault": bool(label),
                    "score": float(score),
                    "is_anomaly": bool(decision),
                }
                for run_id, label, score, decision in zip(
                    run_ids, labels, run_scores, decisions, strict=True
                )
            ],
        }
    )
    return metrics


def localization_metrics(
    metadata: tuple[dict[str, Any], ...], scores: np.ndarray
) -> dict[str, Any]:
    run_service_scores: defaultdict[str, dict[str, float]] = defaultdict(dict)
    expected: defaultdict[str, set[str]] = defaultdict(set)
    scenarios: dict[str, str] = {}
    for item, score in zip(metadata, scores, strict=True):
        if not item["run_has_fault"]:
            continue
        run_id, service = item["run_id"], item["service_name"]
        run_service_scores[run_id][service] = max(
            float(score), run_service_scores[run_id].get(service, float("-inf"))
        )
        configured = item.get("expected_affected_services")
        if isinstance(configured, list):
            expected[run_id].update(configured)
        elif item["is_injected_fault_service"]:
            expected[run_id].add(service)
        scenarios[run_id] = item["scenario"]
    rows: list[dict[str, Any]] = []
    for run_id in sorted(run_service_scores):
        ranking = sorted(
            run_service_scores[run_id],
            key=lambda service: (-run_service_scores[run_id][service], service),
        )
        ranks = [ranking.index(service) + 1 for service in expected[run_id] if service in ranking]
        best_rank = min(ranks) if ranks else None
        rows.append(
            {
                "run_id": run_id,
                "scenario": scenarios[run_id],
                "expected_services": sorted(expected[run_id]),
                "top_services": ranking[:3],
                "best_rank": best_rank,
                "hit_at_1": bool(best_rank and best_rank <= 1),
                "hit_at_3": bool(best_rank and best_rank <= 3),
                "reciprocal_rank": float(1 / best_rank) if best_rank else 0.0,
            }
        )
    return {
        "run_count": len(rows),
        "hit_at_1": float(np.mean([row["hit_at_1"] for row in rows])) if rows else None,
        "hit_at_3": float(np.mean([row["hit_at_3"] for row in rows])) if rows else None,
        "mrr": float(np.mean([row["reciprocal_rank"] for row in rows])) if rows else None,
        "runs": rows,
    }


def scenario_metrics(
    metadata: tuple[dict[str, Any], ...], scores: np.ndarray, threshold: float
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    scenarios = sorted({item["scenario"] for item in metadata if item["run_has_fault"]})
    for scenario in scenarios:
        indices = [
            index
            for index, item in enumerate(metadata)
            if item["scenario"] == scenario and item["is_injected_fault_service"]
        ]
        run_ids = {
            item["run_id"] for item in metadata if item["scenario"] == scenario
        }
        detections = scores[indices] > threshold if indices else np.asarray([], dtype=bool)
        detected_runs = {
            metadata[index]["run_id"]
            for index in indices
            if scores[index] > threshold
        }
        output[scenario] = {
            "target_window_count": len(indices),
            "target_window_recall": float(np.mean(detections)) if len(detections) else None,
            "fault_runs_detected_by_target": len(detected_runs),
            "fault_run_count": len(run_ids),
        }
    return output


def per_service_metrics(
    metadata: tuple[dict[str, Any], ...], scores: np.ndarray, threshold: float
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for service in sorted({item["service_name"] for item in metadata}):
        indices = [
            index
            for index, item in enumerate(metadata)
            if item["service_name"] == service
            and item["ground_truth_role"] in {"normal_negative", "injected_positive"}
        ]
        labels = np.asarray(
            [metadata[index]["is_injected_fault_service"] for index in indices], dtype=bool
        )
        if indices:
            output[service] = binary_metrics(labels, scores[indices], threshold)
    return output


def evaluate_scores(
    metadata: tuple[dict[str, Any], ...], scores: np.ndarray, threshold: float
) -> dict[str, Any]:
    return {
        "service_level": service_level_metrics(metadata, scores, threshold),
        "run_level": run_level_metrics(metadata, scores, threshold),
        "localization": localization_metrics(metadata, scores),
        "per_scenario": scenario_metrics(metadata, scores, threshold),
        "per_service": per_service_metrics(metadata, scores, threshold),
    }
