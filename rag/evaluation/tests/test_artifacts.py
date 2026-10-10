from pathlib import Path

import pytest

from aegis_rag_evaluation.artifacts import (
    load_generation_artifact,
    write_generation_artifact,
)
from aegis_rag_evaluation.benchmark import load_benchmark
from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.errors import ArtifactGuardError
from aegis_rag_evaluation.runner import generate_split

ROOT = Path(__file__).resolve().parents[3]


def payload(config: EvaluationConfig, split: str, variant: str) -> dict:
    bundle = load_benchmark(config)
    pipeline = __import__("json").loads(config.pipeline_config_path.read_text())
    return {
        "benchmark_id": bundle.benchmark_id,
        "query_hash": bundle.query_hash,
        "pipeline_config_hash": bundle.pipeline_hash,
        "corpus_fingerprint": pipeline["corpus"]["fingerprint"],
        "split": split,
        "variant": variant,
        "cases": [{"case_id": case.case_id} for case in bundle.selected(split, variant)],
    }


def test_development_artifact_may_be_replaced(tmp_path: Path) -> None:
    path = tmp_path / "development.json"
    value = {"run": 1}
    write_generation_artifact(path, value, split="development", confirm_final=False)
    write_generation_artifact(path, {"run": 2}, split="development", confirm_final=False)
    assert '"run": 2' in path.read_text()


@pytest.mark.parametrize("variant", ["canonical", "no-reranker-ablation"])
def test_final_artifact_is_confirmation_gated_and_write_once(
    tmp_path: Path, variant: str
) -> None:
    path = tmp_path / f"{variant}.json"
    with pytest.raises(ArtifactGuardError, match="--confirm-final"):
        write_generation_artifact(path, {}, split="final", confirm_final=False)
    write_generation_artifact(path, {}, split="final", confirm_final=True)
    with pytest.raises(ArtifactGuardError, match="write-once"):
        write_generation_artifact(path, {}, split="final", confirm_final=True)


def test_existing_final_is_rejected_before_pipeline_access(tmp_path: Path) -> None:
    config = EvaluationConfig.from_environment(ROOT)
    config = EvaluationConfig(
        repository=config.repository,
        evaluation_root=config.evaluation_root,
        runtime_root=tmp_path,
        model_cache=config.model_cache,
        pipeline_config_path=config.pipeline_config_path,
        evaluator_config_path=config.evaluator_config_path,
    )
    bundle = load_benchmark(config)
    final_path = (
        tmp_path
        / bundle.benchmark_id
        / "generation"
        / "final"
        / "canonical.json"
    )
    final_path.parent.mkdir(parents=True)
    final_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactGuardError, match="write-once"):
        generate_split(
            config,
            bundle,
            "final",
            "canonical",
            None,
            confirm_final=True,
        )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("benchmark_id", "wrong", "benchmark_id mismatch"),
        ("pipeline_config_hash", "wrong", "pipeline_config_hash mismatch"),
        ("corpus_fingerprint", "wrong", "corpus fingerprint mismatch"),
    ],
)
def test_identity_mismatch_fails(tmp_path: Path, key: str, value: str, message: str) -> None:
    config = EvaluationConfig.from_environment(ROOT)
    bundle = load_benchmark(config)
    data = payload(config, "development", "canonical")
    data[key] = value
    path = tmp_path / "artifact.json"
    path.write_text(__import__("json").dumps(data), encoding="utf-8")
    with pytest.raises(ArtifactGuardError, match=message):
        load_generation_artifact(
            path,
            bundle=bundle,
            config=config,
            split="development",
            variant="canonical",
        )
