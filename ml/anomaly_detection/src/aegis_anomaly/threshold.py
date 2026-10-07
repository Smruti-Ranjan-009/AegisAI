from __future__ import annotations

import numpy as np

from .errors import AnomalyError


def calibrate_threshold(normal_scores: np.ndarray, target_fpr: float = 0.05) -> dict[str, float]:
    if normal_scores.ndim != 1 or len(normal_scores) == 0:
        raise AnomalyError("Threshold calibration requires normal validation scores.")
    if not 0 < target_fpr < 1 or not np.all(np.isfinite(normal_scores)):
        raise AnomalyError("Threshold calibration input is invalid.")
    threshold = float(np.quantile(normal_scores, 1.0 - target_fpr, method="higher"))
    observed = float(np.mean(normal_scores > threshold))
    return {
        "target_normal_fpr": target_fpr,
        "threshold": threshold,
        "observed_normal_fpr": observed,
        "normal_score_min": float(np.min(normal_scores)),
        "normal_score_median": float(np.median(normal_scores)),
        "normal_score_p95": float(np.quantile(normal_scores, 0.95)),
        "normal_score_max": float(np.max(normal_scores)),
    }
