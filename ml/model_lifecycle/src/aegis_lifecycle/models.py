from __future__ import annotations

from typing import Any

import joblib
import mlflow
import numpy as np
import pandas as pd

from .errors import LifecycleError


class FrozenAnomalyPyFunc(mlflow.pyfunc.PythonModel):
    """MLflow adapter around the complete trusted Phase 5 bundle."""

    bundle: Any

    def load_context(self, context: Any) -> None:
        self.bundle = joblib.load(context.artifacts["frozen_bundle"])

    def predict(
        self, context: Any, model_input: pd.DataFrame, params: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        del context, params
        expected = tuple(self.bundle.feature_names)
        if tuple(model_input.columns) != expected:
            raise LifecycleError(
                "unsupported_schema", "Anomaly input columns do not match frozen feature order."
            )
        values = model_input.to_numpy(dtype=np.float64)
        values = self.bundle.imputer.transform(values)
        scores = np.asarray(self.bundle.detector.score_samples(values), dtype=np.float64)
        return pd.DataFrame(
            {
                "anomaly_score": scores,
                "is_anomaly": scores > float(self.bundle.threshold),
            }
        )


def anomaly_input_example(bundle: Any) -> pd.DataFrame:
    statistics = np.asarray(bundle.imputer.statistics_, dtype=np.float64)
    if statistics.shape != (len(bundle.feature_names),):
        raise LifecycleError("manifest_invalid", "Frozen anomaly imputer shape is invalid.")
    return pd.DataFrame([statistics], columns=list(bundle.feature_names))


def classifier_input_example(bundle: Any) -> pd.DataFrame:
    imputer = bundle.pipeline.named_steps.get("imputer")
    statistics = np.asarray(getattr(imputer, "statistics_", []), dtype=np.float64)
    if statistics.shape != (len(bundle.feature_names),):
        raise LifecycleError("manifest_invalid", "Frozen classifier imputer shape is invalid.")
    return pd.DataFrame([statistics], columns=list(bundle.feature_names))
