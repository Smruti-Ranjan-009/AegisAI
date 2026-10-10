from __future__ import annotations

import hashlib
import math
from pathlib import Path
from time import perf_counter
from typing import Any

from aegis_rag_evaluation.config import NLI_LABELS, EvaluationConfig
from aegis_rag_evaluation.contracts import NLIPrediction
from aegis_rag_evaluation.errors import EvaluatorUnavailableError


class FakeNLIProvider:
    """Deterministic fake with explicit marker support for tests and hosted CI."""

    model_id = "aegis-fake-nli-v1"
    model_revision = "deterministic-v1"
    load_seconds = 0.0

    def __init__(self, labels: list[str] | None = None) -> None:
        self._labels = list(labels or [])
        self.pairs: list[tuple[str, str]] = []
        self.pairs_scored = 0
        self.inference_seconds = 0.0

    def predict(self, pairs: list[tuple[str, str]]) -> tuple[NLIPrediction, ...]:
        started = perf_counter()
        results = []
        for premise, hypothesis in pairs:
            self.pairs.append((premise, hypothesis))
            if self._labels:
                label = self._labels.pop(0)
            elif "CONTRADICTION" in hypothesis:
                label = "contradiction"
            elif "NEUTRAL" in hypothesis:
                label = "neutral"
            else:
                label = "entailment"
            if label not in NLI_LABELS:
                raise EvaluatorUnavailableError(f"fake NLI returned invalid label: {label}")
            probabilities = {name: 0.05 for name in NLI_LABELS}
            probabilities[label] = 0.9
            results.append(
                NLIPrediction(
                    label=label,
                    probabilities=probabilities,
                    input_tokens=len((premise + " " + hypothesis).split()),
                    truncated=False,
                )
            )
        self.pairs_scored += len(results)
        self.inference_seconds += perf_counter() - started
        return tuple(results)


class DebertaNLIProvider:
    """Pinned safetensors-only CPU NLI adapter with transparent truncation."""

    def __init__(self, config: EvaluationConfig, *, local_files_only: bool = False) -> None:
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise EvaluatorUnavailableError(
                "real NLI requires: pip install -e 'rag/evaluation[models]'"
            ) from exc
        config.model_cache.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        try:
            weight_path = Path(
                hf_hub_download(
                    repo_id=config.nli_model_id,
                    filename=config.nli_filename,
                    revision=config.nli_revision,
                    cache_dir=config.model_cache,
                    local_files_only=local_files_only,
                )
            )
            if _sha256(weight_path) != config.nli_sha256:
                raise EvaluatorUnavailableError("NLI safetensors checksum mismatch")
            self._tokenizer: Any = AutoTokenizer.from_pretrained(
                config.nli_model_id,
                revision=config.nli_revision,
                cache_dir=config.model_cache,
                local_files_only=local_files_only,
                trust_remote_code=False,
            )
            self._model: Any = AutoModelForSequenceClassification.from_pretrained(
                config.nli_model_id,
                revision=config.nli_revision,
                cache_dir=config.model_cache,
                local_files_only=local_files_only,
                trust_remote_code=False,
                use_safetensors=True,
            )
            labels = tuple(self._model.config.id2label[index].lower() for index in range(3))
            if labels != NLI_LABELS:
                raise EvaluatorUnavailableError(f"unexpected NLI label order: {labels}")
            self._model.to(config.nli_device)
            self._model.eval()
            self._torch = torch
        except EvaluatorUnavailableError:
            raise
        except Exception as exc:
            raise EvaluatorUnavailableError(f"unable to load pinned NLI model: {exc}") from exc
        self._config = config
        self._load_seconds = perf_counter() - started
        self.pairs_scored = 0
        self.inference_seconds = 0.0

    @property
    def model_id(self) -> str:
        return self._config.nli_model_id

    @property
    def model_revision(self) -> str:
        return self._config.nli_revision

    @property
    def load_seconds(self) -> float:
        return self._load_seconds

    def predict(self, pairs: list[tuple[str, str]]) -> tuple[NLIPrediction, ...]:
        if not pairs:
            return ()
        started = perf_counter()
        results: list[NLIPrediction] = []
        try:
            for premise, hypothesis in pairs:
                raw_tokens = self._tokenizer(
                    premise, hypothesis, add_special_tokens=True, truncation=False
                )["input_ids"]
                encoded = self._tokenizer(
                    premise,
                    hypothesis,
                    return_tensors="pt",
                    truncation="longest_first",
                    max_length=self._config.nli_max_length,
                )
                encoded = {key: value.to(self._config.nli_device) for key, value in encoded.items()}
                with self._torch.inference_mode():
                    probabilities = self._torch.softmax(self._model(**encoded).logits, dim=-1)[
                        0
                    ].tolist()
                index = max(range(3), key=probabilities.__getitem__)
                results.append(
                    NLIPrediction(
                        label=NLI_LABELS[index],
                        probabilities={
                            label: float(probabilities[position])
                            for position, label in enumerate(NLI_LABELS)
                        },
                        input_tokens=int(encoded["input_ids"].shape[1]),
                        truncated=len(raw_tokens) > self._config.nli_max_length,
                    )
                )
        except Exception as exc:
            raise EvaluatorUnavailableError(f"NLI inference failed: {exc}") from exc
        if len(results) != len(pairs) or any(
            not math.isclose(sum(result.probabilities.values()), 1.0, abs_tol=1e-4)
            for result in results
        ):
            raise EvaluatorUnavailableError("NLI returned malformed probabilities")
        self.pairs_scored += len(results)
        self.inference_seconds += perf_counter() - started
        return tuple(results)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
