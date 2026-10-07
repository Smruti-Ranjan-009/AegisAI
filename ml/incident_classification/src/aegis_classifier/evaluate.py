from __future__ import annotations

import time
from typing import Any

import numpy as np
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
    roc_auc_score,
    top_k_accuracy_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline

from .config import CLASS_NAMES, TrainingConfig
from .errors import ClassificationError


def ordered_probabilities(
    pipeline: Pipeline, values: np.ndarray, class_names: tuple[str, ...] = CLASS_NAMES
) -> np.ndarray:
    probabilities = np.asarray(pipeline.predict_proba(values), dtype=np.float64)
    fitted_classes = tuple(str(value) for value in pipeline.named_steps["classifier"].classes_)
    if set(fitted_classes) != set(class_names):
        raise ClassificationError("Fitted classifier class vocabulary is incomplete.")
    indices = [fitted_classes.index(name) for name in class_names]
    ordered = probabilities[:, indices]
    if not np.all(np.isfinite(ordered)) or not np.allclose(ordered.sum(axis=1), 1.0):
        raise ClassificationError("Classifier emitted invalid probabilities.")
    return ordered


def classification_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    class_names: tuple[str, ...] = CLASS_NAMES,
) -> dict[str, Any]:
    if labels.ndim != 1 or probabilities.shape != (len(labels), len(class_names)):
        raise ClassificationError("Evaluation labels/probabilities are not aligned.")
    if set(labels) != set(class_names):
        raise ClassificationError("Evaluation requires every supported incident class.")
    predicted = np.asarray([class_names[index] for index in np.argmax(probabilities, axis=1)])
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predicted, labels=class_names, zero_division=0
    )
    matrix = confusion_matrix(labels, predicted, labels=class_names)
    encoded = np.asarray([class_names.index(str(label)) for label in labels], dtype=int)
    return {
        "row_count": len(labels),
        "accuracy": float(accuracy_score(labels, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, predicted)),
        "macro_precision": float(
            precision_score(labels, predicted, average="macro", zero_division=0)
        ),
        "macro_recall": float(recall_score(labels, predicted, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(labels, predicted, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(labels, predicted, average="weighted", zero_division=0)
        ),
        "top_2_accuracy": float(
            top_k_accuracy_score(encoded, probabilities, k=2, labels=list(range(len(class_names))))
        ),
        "roc_auc_ovr_macro": float(
            roc_auc_score(
                np.column_stack([labels == name for name in class_names]),
                probabilities,
                average="macro",
            )
        ),
        "log_loss": float(
            log_loss(encoded, probabilities, labels=list(range(len(class_names))))
        ),
        "class_order": list(class_names),
        "confusion_matrix": matrix.tolist(),
        "per_class": {
            name: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
                "correct": int(matrix[index, index]),
            }
            for index, name in enumerate(class_names)
        },
        "predicted_classes": predicted.tolist(),
    }


def cross_validate_pipeline(
    name: str,
    pipeline: Pipeline,
    values: np.ndarray,
    labels: np.ndarray,
    config: TrainingConfig | None = None,
) -> dict[str, Any]:
    config = config or TrainingConfig()
    splitter = StratifiedKFold(
        n_splits=config.cv_splits,
        shuffle=True,
        random_state=config.random_state,
    )
    oof = np.zeros((len(labels), len(CLASS_NAMES)), dtype=np.float64)
    fold_results: list[dict[str, Any]] = []
    started = time.perf_counter()
    for fold, (train_indices, validation_indices) in enumerate(
        splitter.split(values, labels), start=1
    ):
        fold_pipeline = clone(pipeline)
        fold_pipeline.fit(values[train_indices], labels[train_indices])
        probabilities = ordered_probabilities(fold_pipeline, values[validation_indices])
        oof[validation_indices] = probabilities
        metrics = classification_metrics(labels[validation_indices], probabilities)
        fold_results.append(
            {
                "fold": fold,
                "training_rows": len(train_indices),
                "validation_rows": len(validation_indices),
                "macro_f1": metrics["macro_f1"],
                "balanced_accuracy": metrics["balanced_accuracy"],
                "accuracy": metrics["accuracy"],
                "top_2_accuracy": metrics["top_2_accuracy"],
            }
        )
    duration = time.perf_counter() - started
    oof_metrics = classification_metrics(labels, oof)
    macro_values = np.asarray([item["macro_f1"] for item in fold_results])
    return {
        "model": name,
        "n_splits": config.cv_splits,
        "shuffle": True,
        "random_state": config.random_state,
        "preprocessing_fit_scope": "inside each fold pipeline",
        "duration_seconds": duration,
        "macro_f1_mean": float(macro_values.mean()),
        "macro_f1_std": float(macro_values.std()),
        "balanced_accuracy_mean": float(
            np.mean([item["balanced_accuracy"] for item in fold_results])
        ),
        "accuracy_mean": float(np.mean([item["accuracy"] for item in fold_results])),
        "top_2_accuracy_mean": float(
            np.mean([item["top_2_accuracy"] for item in fold_results])
        ),
        "folds": fold_results,
        "out_of_fold": oof_metrics,
    }
