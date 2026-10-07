from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline

from .config import TrainingConfig
from .preprocessing import forest_preprocessing


def build_random_forest_pipeline(config: TrainingConfig | None = None) -> Pipeline:
    config = config or TrainingConfig()
    classifier = RandomForestClassifier(
        n_estimators=config.forest_estimators,
        max_depth=config.forest_max_depth,
        min_samples_leaf=config.forest_min_samples_leaf,
        random_state=config.random_state,
        class_weight="balanced_subsample",
        n_jobs=1,
    )
    return forest_preprocessing(classifier)
