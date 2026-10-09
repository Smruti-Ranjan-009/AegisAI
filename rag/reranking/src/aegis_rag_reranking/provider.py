from __future__ import annotations

import hashlib
from time import perf_counter


class FakeRerankerProvider:
    """Stable network-free scorer used by unit tests and hosted CI."""

    model_id = "aegis-fake-reranker-v1"
    model_revision = "deterministic-v1"

    def __init__(self, scores: dict[str, float] | None = None) -> None:
        self._scores = scores or {}
        self._loaded_at = perf_counter()

    @property
    def load_seconds(self) -> float:
        return 0.0

    def score(self, query: str, passages: list[str]) -> tuple[float, ...]:
        values: list[float] = []
        for passage in passages:
            if passage in self._scores:
                values.append(self._scores[passage])
                continue
            digest = hashlib.sha256(f"{query}\0{passage}".encode()).digest()
            values.append(int.from_bytes(digest[:8], "big") / (2**64 - 1))
        return tuple(values)
