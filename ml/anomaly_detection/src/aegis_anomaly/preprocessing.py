from __future__ import annotations

import numpy as np

from .errors import AnomalyError


class MedianImputer:
    def __init__(self) -> None:
        self.statistics_: np.ndarray | None = None

    def fit(self, values: np.ndarray) -> MedianImputer:
        if values.ndim != 2 or values.shape[0] == 0:
            raise AnomalyError("Cannot fit imputer on an empty or non-matrix input.")
        statistics = np.empty(values.shape[1], dtype=np.float64)
        for index in range(values.shape[1]):
            present = values[:, index][~np.isnan(values[:, index])]
            statistics[index] = float(np.median(present)) if len(present) else 0.0
        if not np.all(np.isfinite(statistics)):
            raise AnomalyError("Imputer learned a non-finite statistic.")
        self.statistics_ = statistics
        return self

    def transform(self, values: np.ndarray) -> np.ndarray:
        if self.statistics_ is None:
            raise AnomalyError("Median imputer must be fitted before transform.")
        if values.ndim != 2 or values.shape[1] != len(self.statistics_):
            raise AnomalyError("Imputer input feature count does not match fitted state.")
        result = np.asarray(values, dtype=np.float64).copy()
        missing = np.isnan(result)
        if missing.any():
            result[missing] = np.take(self.statistics_, np.where(missing)[1])
        if not np.all(np.isfinite(result)):
            raise AnomalyError("Preprocessed matrix contains non-finite values.")
        return result

    def fit_transform(self, values: np.ndarray) -> np.ndarray:
        return self.fit(values).transform(values)
