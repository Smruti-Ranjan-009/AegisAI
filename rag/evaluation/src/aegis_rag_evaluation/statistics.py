from __future__ import annotations

import random
from collections.abc import Callable, Sequence


def bootstrap_interval(
    values: Sequence[float],
    *,
    resamples: int = 10_000,
    seed: int = 11_042,
    confidence: float = 0.95,
) -> dict[str, float | int]:
    if not values:
        raise ValueError("bootstrap input must not be empty")
    return _bootstrap(
        list(values),
        lambda sample: sum(sample) / len(sample),
        resamples,
        seed,
        confidence,
    )


def paired_bootstrap_difference(
    canonical: Sequence[float],
    ablation: Sequence[float],
    *,
    resamples: int = 10_000,
    seed: int = 11_042,
    confidence: float = 0.95,
) -> dict[str, float | int]:
    if not canonical or len(canonical) != len(ablation):
        raise ValueError("paired bootstrap inputs must be non-empty and equally sized")
    differences = [left - right for left, right in zip(canonical, ablation, strict=True)]
    return _bootstrap(
        differences, lambda sample: sum(sample) / len(sample), resamples, seed, confidence
    )


def _bootstrap(
    values: list[float],
    statistic: Callable[[list[float]], float],
    resamples: int,
    seed: int,
    confidence: float,
) -> dict[str, float | int]:
    if resamples <= 0 or not 0 < confidence < 1:
        raise ValueError("invalid bootstrap configuration")
    observed = statistic(values)
    if len(values) == 1:
        return {
            "estimate": observed,
            "lower": observed,
            "upper": observed,
            "resamples": resamples,
            "seed": seed,
        }
    rng = random.Random(seed)
    estimates = sorted(
        statistic([values[rng.randrange(len(values))] for _ in values])
        for _ in range(resamples)
    )
    alpha = (1 - confidence) / 2
    lower = estimates[int(alpha * (resamples - 1))]
    upper = estimates[int((1 - alpha) * (resamples - 1))]
    return {
        "estimate": observed,
        "lower": lower,
        "upper": upper,
        "resamples": resamples,
        "seed": seed,
    }
