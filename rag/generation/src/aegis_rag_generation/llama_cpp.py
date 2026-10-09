from __future__ import annotations

import hashlib
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.contracts import SLMGeneration
from aegis_rag_generation.errors import ModelIntegrityError, SLMUnavailableError
from aegis_rag_generation.schema import RawGroundedResponse


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_model_file(config: GenerationConfig) -> dict[str, Any]:
    if not config.model_path.is_file():
        raise ModelIntegrityError(f"GGUF does not exist: {config.model_path}")
    actual = sha256_file(config.model_path)
    if actual != config.model_sha256:
        raise ModelIntegrityError(
            f"GGUF checksum mismatch: expected {config.model_sha256}, got {actual}"
        )
    return {
        "repository": config.model_repository,
        "revision": config.model_revision,
        "filename": config.model_filename,
        "quantization": config.quantization,
        "path": str(config.model_path),
        "size_bytes": config.model_path.stat().st_size,
        "sha256": actual,
        "valid": True,
    }


class LocalLlamaCppProvider:
    def __init__(self, config: GenerationConfig) -> None:
        self.config = config
        self.client = httpx.Client(base_url=config.endpoint, timeout=config.timeout_seconds)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()
            value = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SLMUnavailableError(f"local llama.cpp request failed: {exc}") from exc
        if not isinstance(value, dict):
            raise SLMUnavailableError("local llama.cpp returned a non-object response")
        return value

    def health(self) -> dict[str, Any]:
        value = self._request("GET", "/health")
        if value.get("status") not in {"ok", "no slot available"}:
            raise SLMUnavailableError(f"unexpected llama.cpp health: {value.get('status')}")
        info = self.model_info()
        return {"status": value.get("status"), "local_only": True, "model": info}

    def model_info(self) -> dict[str, Any]:
        value = self._request("GET", "/v1/models")
        models = value.get("data")
        if not isinstance(models, list) or not models:
            raise SLMUnavailableError("llama.cpp did not report a loaded model")
        identifiers = [str(item.get("id", "")) for item in models if isinstance(item, dict)]
        if self.config.model_alias not in identifiers:
            raise SLMUnavailableError(
                f"expected model alias {self.config.model_alias}; loaded {identifiers}"
            )
        return {
            "expected_alias": self.config.model_alias,
            "loaded_model_ids": identifiers,
            "repository": self.config.model_repository,
            "revision": self.config.model_revision,
            "filename": self.config.model_filename,
            "sha256": self.config.model_sha256,
        }

    def count_tokens(self, system_prompt: str, user_prompt: str) -> int:
        template = self._request(
            "POST",
            "/apply-template",
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        prompt = template.get("prompt")
        if not isinstance(prompt, str):
            raise SLMUnavailableError("llama.cpp did not return the applied chat template")
        tokenized = self._request(
            "POST",
            "/tokenize",
            json={"content": prompt, "add_special": False, "parse_special": True},
        )
        tokens = tokenized.get("tokens")
        if not isinstance(tokens, list):
            raise SLMUnavailableError("llama.cpp did not return prompt tokens")
        return len(tokens)

    def generate(self, system_prompt: str, user_prompt: str) -> SLMGeneration:
        started = perf_counter()
        value = self._request(
            "POST",
            "/v1/chat/completions",
            json={
                "model": self.config.model_alias,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "seed": self.config.seed,
                "max_tokens": self.config.max_output_tokens,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "none",
                "response_format": {
                    "type": "json_object",
                    "schema": RawGroundedResponse.model_json_schema(),
                },
            },
        )
        total = perf_counter() - started
        try:
            text = value["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SLMUnavailableError("llama.cpp completion response is missing content") from exc
        if not isinstance(text, str) or not text.strip():
            raise SLMUnavailableError("llama.cpp completion content is empty")
        usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
        timings = value.get("timings") if isinstance(value.get("timings"), dict) else {}
        prompt_tokens = _optional_int(usage.get("prompt_tokens", timings.get("prompt_n")))
        generated_tokens = _optional_int(
            usage.get("completion_tokens", timings.get("predicted_n"))
        )
        tokens_per_second = _optional_float(timings.get("predicted_per_second"))
        return SLMGeneration(
            text=text,
            prompt_tokens=prompt_tokens,
            generated_tokens=generated_tokens,
            total_seconds=total,
            time_to_first_token_seconds=None,
            tokens_per_second=tokens_per_second,
        )


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None
