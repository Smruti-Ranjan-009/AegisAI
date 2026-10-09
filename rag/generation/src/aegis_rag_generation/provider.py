from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from aegis_rag_generation.contracts import SLMGeneration


class FakeSLMProvider:
    """Deterministic injectable local-provider substitute for tests and CI."""

    def __init__(
        self,
        response: str | dict[str, Any] | Callable[[str, str], str],
        *,
        token_count: int | Callable[[str, str], int] | None = None,
        unavailable: bool = False,
    ) -> None:
        self.response = response
        self.token_count = token_count
        self.unavailable = unavailable
        self.generate_calls = 0
        self.last_system_prompt = ""
        self.last_user_prompt = ""

    def health(self) -> dict[str, Any]:
        if self.unavailable:
            raise RuntimeError("fake SLM unavailable")
        return {"status": "ok", "local_only": True}

    def model_info(self) -> dict[str, Any]:
        return {"id": "aegis-fake-slm-v1", "runtime": "fake"}

    def count_tokens(self, system_prompt: str, user_prompt: str) -> int:
        if callable(self.token_count):
            return self.token_count(system_prompt, user_prompt)
        if isinstance(self.token_count, int):
            return self.token_count
        return len((system_prompt + "\n" + user_prompt).split())

    def generate(self, system_prompt: str, user_prompt: str) -> SLMGeneration:
        if self.unavailable:
            raise RuntimeError("fake SLM unavailable")
        self.generate_calls += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if callable(self.response):
            text = self.response(system_prompt, user_prompt)
        elif isinstance(self.response, dict):
            text = json.dumps(self.response)
        else:
            text = self.response
        return SLMGeneration(
            text=text,
            prompt_tokens=self.count_tokens(system_prompt, user_prompt),
            generated_tokens=len(text.split()),
            total_seconds=0.001,
            time_to_first_token_seconds=None,
            tokens_per_second=1000.0,
        )
