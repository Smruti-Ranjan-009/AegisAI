from __future__ import annotations

import re

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class DeterministicTokenizer:
    """Small reversible tokenizer for tests and dependency-light inspection."""

    def __init__(self) -> None:
        self._token_to_id: dict[str, int] = {}
        self._id_to_token: dict[int, str] = {}

    @property
    def identity(self) -> str:
        return "aegis-deterministic-tokenizer-v1"

    def encode(self, text: str) -> list[int]:
        result: list[int] = []
        for token in TOKEN_PATTERN.findall(text):
            token_id = self._token_to_id.setdefault(token, len(self._token_to_id) + 1)
            self._id_to_token[token_id] = token
            result.append(token_id)
        return result

    def decode(self, token_ids: list[int]) -> str:
        tokens = [self._id_to_token[token_id] for token_id in token_ids]
        text = " ".join(tokens)
        return re.sub(r"\s+([,.;:!?%)\]])", r"\1", text).strip()
