from __future__ import annotations

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from .config import TrainingConfig
from .preprocessing import logistic_preprocessing


def build_logistic_pipeline(config: TrainingConfig | None = None) -> Pipeline:
    config = config or TrainingConfig()
    classifier = LogisticRegression(
        max_iter=config.logistic_max_iter,
        random_state=config.random_state,
        solver="lbfgs",
    )
    return logistic_preprocessing(classifier)
