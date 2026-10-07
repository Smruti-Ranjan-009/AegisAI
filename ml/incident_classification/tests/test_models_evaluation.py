from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import clone

from aegis_classifier.config import CLASS_NAMES, TrainingConfig
from aegis_classifier.errors import ClassificationError
from aegis_classifier.evaluate import (
    classification_metrics,
    cross_validate_pipeline,
    ordered_probabilities,
)
from aegis_classifier.logistic_model import build_logistic_pipeline
from aegis_classifier.random_forest_model import build_random_forest_pipeline


@pytest.mark.parametrize(
    "factory,expected_steps",
    [
        (build_logistic_pipeline, ["imputer", "scaler", "classifier"]),
        (build_random_forest_pipeline, ["imputer", "classifier"]),
    ],
)
def test_candidate_fit_predict_probability_and_determinism(
    separable_values, factory, expected_steps
) -> None:
    values, labels = separable_values
    first = factory().fit(values, labels)
    second = factory().fit(values, labels)
    assert list(first.named_steps) == expected_steps
    probabilities = ordered_probabilities(first, values)
    assert probabilities.shape == (len(values), len(CLASS_NAMES))
    assert np.all(np.isfinite(probabilities))
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert np.array_equal(probabilities, ordered_probabilities(second, values))
    assert tuple(first.named_steps["classifier"].classes_) == tuple(sorted(CLASS_NAMES))
    if factory is build_random_forest_pipeline:
        assert first.named_steps["classifier"].feature_importances_.shape == (values.shape[1],)


def test_cross_validation_fits_complete_pipeline_inside_each_fold(separable_values) -> None:
    values, labels = separable_values
    pipeline = build_logistic_pipeline()
    result = cross_validate_pipeline(
        "logistic_regression", pipeline, values, labels, TrainingConfig(cv_splits=4)
    )
    assert result["preprocessing_fit_scope"] == "inside each fold pipeline"
    assert len(result["folds"]) == 4
    assert not hasattr(pipeline.named_steps["imputer"], "statistics_")
    assert all(fold["training_rows"] == 30 for fold in result["folds"])


def test_evaluation_reports_complete_multiclass_metrics(separable_values) -> None:
    values, labels = separable_values
    pipeline = build_logistic_pipeline().fit(values, labels)
    result = classification_metrics(labels, ordered_probabilities(pipeline, values))
    assert result["accuracy"] == pytest.approx(1.0)
    assert result["top_2_accuracy"] == pytest.approx(1.0)
    assert len(result["confusion_matrix"]) == 5
    assert set(result["per_class"]) == set(CLASS_NAMES)
    assert result["roc_auc_ovr_macro"] == pytest.approx(1.0)


def test_evaluation_rejects_missing_class_fixture() -> None:
    labels = np.asarray(CLASS_NAMES[:-1])
    probabilities = np.full((4, 5), 0.2)
    with pytest.raises(ClassificationError, match="every supported"):
        classification_metrics(labels, probabilities)


def test_models_handle_missing_values_through_fold_local_imputation(separable_values) -> None:
    values, labels = separable_values
    values = values.copy()
    values[0, 0] = np.nan
    for pipeline in (build_logistic_pipeline(), build_random_forest_pipeline()):
        fitted = clone(pipeline).fit(values, labels)
        assert np.all(np.isfinite(ordered_probabilities(fitted, values)))
