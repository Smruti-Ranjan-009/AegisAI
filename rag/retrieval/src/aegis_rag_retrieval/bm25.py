from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from rank_bm25 import BM25Okapi

from aegis_rag_retrieval.contracts import ChunkRecord, RankedChunk, SearchFilters
from aegis_rag_retrieval.tokenizer import tokenize


class BM25Index:
    def __init__(
        self,
        chunks: tuple[ChunkRecord, ...],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: Callable[[str], list[str]] = tokenize,
    ) -> None:
        started = perf_counter()
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer
        self.tokenized_corpus = [tokenizer(chunk.lexical_text) for chunk in chunks]
        self._index = BM25Okapi(self.tokenized_corpus, k1=k1, b=b)
        self.build_seconds = perf_counter() - started

    def search(
        self,
        query: str,
        *,
        limit: int,
        filters: SearchFilters,
    ) -> tuple[RankedChunk, ...]:
        scores = self._index.get_scores(self.tokenizer(query))
        eligible = (
            (float(scores[index]), chunk)
            for index, chunk in enumerate(self.chunks)
            if filters.matches(chunk)
        )
        ordered = sorted(eligible, key=lambda item: (-item[0], item[1].chunk_id))[:limit]
        return tuple(
            RankedChunk(chunk=chunk, rank=rank, score=score)
            for rank, (score, chunk) in enumerate(ordered, start=1)
        )

