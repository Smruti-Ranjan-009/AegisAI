from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from aegis_lifecycle.errors import LifecycleError
from aegis_lifecycle.models import FrozenAnomalyPyFunc, anomaly_input_example


class FakeImputer:
    def __init__(self) -> None:
        self.statistics_ = np.asarray([0.5, 1.0])

    def transform(self, values: np.ndarray) -> np.ndarray:
        return np.where(np.isnan(values), self.statistics_, values)


class FakeDetector:
    def score_samples(self, values: np.ndarray) -> np.ndarray:
        return values.mean(axis=1)


@dataclass
class FakeBundle:
    feature_names: tuple[str, ...] = ("first", "second")
    imputer: FakeImputer = FakeImputer()
    detector: FakeDetector = FakeDetector()
    threshold: float = 0.75


def test_anomaly_wrapper_preserves_order_score_and_strict_threshold() -> None:
    wrapper = FrozenAnomalyPyFunc()
    wrapper.bundle = FakeBundle()
    inputs = pd.DataFrame([[0.5, 1.0], [1.0, 1.0]], columns=["first", "second"])
    result = wrapper.predict(None, inputs)
    assert result["anomaly_score"].tolist() == [0.75, 1.0]
    assert result["is_anomaly"].tolist() == [False, True]


def test_anomaly_wrapper_rejects_reordered_features() -> None:
    wrapper = FrozenAnomalyPyFunc()
    wrapper.bundle = FakeBundle()
    with pytest.raises(LifecycleError, match="unsupported_schema"):
        wrapper.predict(None, pd.DataFrame([[1.0, 0.5]], columns=["second", "first"]))


def test_anomaly_input_example_uses_fitted_imputer() -> None:
    example = anomaly_input_example(FakeBundle())
    assert list(example.columns) == ["first", "second"]
    assert example.iloc[0].tolist() == [0.5, 1.0]
