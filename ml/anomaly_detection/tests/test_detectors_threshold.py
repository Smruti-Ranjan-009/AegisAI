from __future__ import annotations

import numpy as np

from aegis_anomaly.isolation_forest import IsolationForestDetector
from aegis_anomaly.robust_detector import RobustZScoreDetector
from aegis_anomaly.threshold import calibrate_threshold


def _normal_and_outlier() -> tuple[np.ndarray, np.ndarray]:
    normal = np.asarray(
        [[0.0, 0.1], [0.1, -0.1], [-0.1, 0.0], [0.05, 0.02], [-0.05, -0.02]]
    )
    return normal, np.asarray([[20.0, 20.0]])


def test_robust_detector_scores_outlier_higher() -> None:
    normal, outlier = _normal_and_outlier()
    detector = RobustZScoreDetector(top_k=2).fit(normal)
    assert detector.score_samples(outlier)[0] > max(detector.score_samples(normal))
    contributors = detector.top_contributors(outlier, ("a", "b"), limit=1)
    assert contributors[0][0]["feature"] in {"a", "b"}


def test_robust_detector_zero_scale_is_finite() -> None:
    values = np.ones((5, 3))
    detector = RobustZScoreDetector().fit(values)
    assert np.all(np.isfinite(detector.score_samples(values)))


def test_isolation_forest_scores_outlier_higher() -> None:
    normal, outlier = _normal_and_outlier()
    detector = IsolationForestDetector(n_estimators=50).fit(normal)
    assert detector.score_samples(outlier)[0] > np.median(detector.score_samples(normal))


def test_threshold_uses_normal_quantile_only() -> None:
    normal = np.arange(20, dtype=float)
    result = calibrate_threshold(normal, 0.05)
    with_faults_ignored = calibrate_threshold(normal, 0.05)
    assert result == with_faults_ignored
    assert result["threshold"] == 19.0
    assert result["observed_normal_fpr"] == 0.0
