from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from .config import RANDOM_STATE
from .errors import AnomalyError


class IsolationForestDetector:
    def __init__(self, n_estimators: int = 300, random_state: int = RANDOM_STATE) -> None:
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model = IsolationForest(
            n_estimators=n_estimators,
            max_samples="auto",
            contamination="auto",
            random_state=random_state,
            n_jobs=1,
        )
        self.fitted_ = False

    def fit(self, values: np.ndarray) -> IsolationForestDetector:
        if values.ndim != 2 or values.shape[0] == 0 or not np.all(np.isfinite(values)):
            raise AnomalyError("Isolation Forest requires a non-empty finite matrix.")
        self.model.fit(values)
        self.fitted_ = True
        return self

    def score_samples(self, values: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise AnomalyError("Isolation Forest must be fitted before scoring.")
        return -self.model.score_samples(values)
