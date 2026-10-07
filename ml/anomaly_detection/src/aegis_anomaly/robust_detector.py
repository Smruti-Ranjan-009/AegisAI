from __future__ import annotations

import numpy as np

from .errors import AnomalyError


class RobustZScoreDetector:
    def __init__(self, top_k: int = 5) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        self.top_k = top_k
        self.medians_: np.ndarray | None = None
        self.scales_: np.ndarray | None = None

    def fit(self, values: np.ndarray) -> RobustZScoreDetector:
        if values.ndim != 2 or values.shape[0] == 0 or not np.all(np.isfinite(values)):
            raise AnomalyError("Robust detector requires a non-empty finite matrix.")
        medians = np.median(values, axis=0)
        scales = np.median(np.abs(values - medians), axis=0) * 1.4826
        for index in np.flatnonzero(scales <= 0):
            q25, q75 = np.quantile(values[:, index], [0.25, 0.75])
            iqr_scale = (q75 - q25) / 1.349
            scales[index] = iqr_scale if iqr_scale > 0 else 1.0
        self.medians_ = medians.astype(np.float64)
        self.scales_ = scales.astype(np.float64)
        return self

    def deviations(self, values: np.ndarray) -> np.ndarray:
        if self.medians_ is None or self.scales_ is None:
            raise AnomalyError("Robust detector must be fitted before scoring.")
        return np.abs((values - self.medians_) / self.scales_)

    def score_samples(self, values: np.ndarray) -> np.ndarray:
        deviations = self.deviations(values)
        k = min(self.top_k, deviations.shape[1])
        selected = np.partition(deviations, deviations.shape[1] - k, axis=1)[:, -k:]
        return np.mean(selected, axis=1)

    def top_contributors(
        self, values: np.ndarray, feature_names: tuple[str, ...], limit: int = 5
    ) -> list[list[dict[str, float | str]]]:
        deviations = self.deviations(values)
        output: list[list[dict[str, float | str]]] = []
        for row in deviations:
            indices = np.argsort(row)[::-1][:limit]
            output.append(
                [
                    {"feature": feature_names[index], "absolute_robust_z": float(row[index])}
                    for index in indices
                ]
            )
        return output
