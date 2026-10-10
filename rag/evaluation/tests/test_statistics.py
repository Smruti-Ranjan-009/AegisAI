import pytest

from aegis_rag_evaluation.statistics import bootstrap_interval, paired_bootstrap_difference


def test_bootstrap_is_fixed_seed_deterministic() -> None:
    first = bootstrap_interval([0.0, 0.5, 1.0], resamples=200, seed=42)
    second = bootstrap_interval([0.0, 0.5, 1.0], resamples=200, seed=42)
    assert first == second


def test_paired_bootstrap_preserves_pair_differences() -> None:
    result = paired_bootstrap_difference([3.0, 4.0], [1.0, 2.0], resamples=200)
    assert result["estimate"] == 2
    assert result["lower"] == 2
    assert result["upper"] == 2


def test_empty_bootstrap_fails_and_one_sample_is_degenerate() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        bootstrap_interval([])
    assert bootstrap_interval([0.75])["lower"] == 0.75
