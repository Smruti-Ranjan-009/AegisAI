from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.contracts import BenchmarkBundle, Split, Variant
from aegis_rag_evaluation.errors import ArtifactGuardError


def generation_path(
    config: EvaluationConfig, bundle: BenchmarkBundle, split: Split, variant: Variant
) -> Path:
    return config.runtime_root / bundle.benchmark_id / "generation" / split / f"{variant}.json"


def score_path(
    config: EvaluationConfig, bundle: BenchmarkBundle, split: Split, variant: Variant
) -> Path:
    return config.runtime_root / bundle.benchmark_id / "scores" / split / f"{variant}.json"


def write_generation_artifact(
    path: Path,
    value: dict[str, Any],
    *,
    split: Split,
    confirm_final: bool,
) -> None:
    if split == "final" and not confirm_final:
        raise ArtifactGuardError("final generation requires --confirm-final")
    if split == "final" and path.exists():
        raise ArtifactGuardError(f"final artifact is write-once and already exists: {path}")
    _atomic_json(path, value, replace=split == "development")


def write_score_artifact(path: Path, value: dict[str, Any]) -> None:
    _atomic_json(path, value, replace=True)


def load_generation_artifact(
    path: Path,
    *,
    bundle: BenchmarkBundle,
    config: EvaluationConfig,
    split: Split,
    variant: Variant,
    corpus_fingerprint: str | None = None,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactGuardError(f"unable to load generation artifact {path}: {exc}") from exc
    expected = {
        "benchmark_id": bundle.benchmark_id,
        "query_hash": bundle.query_hash,
        "pipeline_config_hash": bundle.pipeline_hash,
        "split": split,
        "variant": variant,
    }
    for key, required in expected.items():
        if value.get(key) != required:
            raise ArtifactGuardError(
                f"artifact {key} mismatch: expected {required}, got {value.get(key)}"
            )
    pipeline = json.loads(config.pipeline_config_path.read_text(encoding="utf-8"))
    expected_corpus = corpus_fingerprint or pipeline["corpus"]["fingerprint"]
    if value.get("corpus_fingerprint") != expected_corpus:
        raise ArtifactGuardError("artifact corpus fingerprint mismatch")
    expected_cases = {case.case_id for case in bundle.selected(split, variant)}
    actual_cases = {case.get("case_id") for case in value.get("cases", [])}
    if expected_cases != actual_cases:
        raise ArtifactGuardError("artifact case set mismatch")
    return value


def _atomic_json(path: Path, value: dict[str, Any], *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise ArtifactGuardError(f"refusing to overwrite {path}")
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
