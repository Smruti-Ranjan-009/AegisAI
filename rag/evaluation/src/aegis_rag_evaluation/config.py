from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

NLI_MODEL_ID = "cross-encoder/nli-deberta-v3-small"
NLI_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
NLI_FILENAME = "model.safetensors"
NLI_SHA256 = "ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86"
NLI_LABELS = ("contradiction", "entailment", "neutral")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class EvaluationConfig:
    repository: Path
    evaluation_root: Path
    runtime_root: Path
    model_cache: Path
    pipeline_config_path: Path
    evaluator_config_path: Path
    nli_model_id: str = NLI_MODEL_ID
    nli_revision: str = NLI_REVISION
    nli_filename: str = NLI_FILENAME
    nli_sha256: str = NLI_SHA256
    nli_device: str = "cpu"
    nli_max_length: int = 512
    bootstrap_resamples: int = 10_000
    bootstrap_seed: int = 11_042

    @classmethod
    def from_environment(cls, root: Path | None = None) -> EvaluationConfig:
        repo = (root or repository_root()).resolve()
        evaluation = repo / "rag" / "evaluation"
        return cls(
            repository=repo,
            evaluation_root=evaluation,
            runtime_root=Path(
                os.getenv("AEGIS_RAG_EVALUATION_RUNTIME_ROOT")
                or repo / ".runtime" / "rag" / "evaluation"
            ).resolve(),
            model_cache=Path(
                os.getenv("AEGIS_RAG_NLI_MODEL_CACHE")
                or repo / ".runtime" / "rag" / "huggingface" / "nli"
            ).resolve(),
            pipeline_config_path=evaluation / "phase11_pipeline_config.json",
            evaluator_config_path=evaluation / "phase11_evaluator_config.json",
            nli_device=os.getenv("AEGIS_RAG_NLI_DEVICE") or "cpu",
        )

    @property
    def pipeline_hash(self) -> str:
        return sha256_file(self.pipeline_config_path)

    @property
    def evaluator_hash(self) -> str:
        return sha256_file(self.evaluator_config_path)
