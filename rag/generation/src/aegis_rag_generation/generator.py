from __future__ import annotations

from time import perf_counter
from typing import Any

from aegis_rag_reranking.reranker import RerankingPipeline
from aegis_rag_retrieval.contracts import SearchFilters

from aegis_rag_generation.citations import parse_and_validate
from aegis_rag_generation.config import GenerationConfig
from aegis_rag_generation.contracts import (
    EvidenceItem,
    GenerationOutcome,
    SLMProvider,
)
from aegis_rag_generation.errors import ContextBudgetError, SLMUnavailableError
from aegis_rag_generation.evidence import build_evidence_pack
from aegis_rag_generation.prompt import SYSTEM_PROMPT, render_user_prompt
from aegis_rag_generation.schema import GroundedResponse


def fit_context(
    query: str,
    evidence: tuple[EvidenceItem, ...],
    provider: SLMProvider,
    config: GenerationConfig,
) -> tuple[tuple[EvidenceItem, ...], tuple[str, ...], str, int]:
    retained = list(evidence)
    dropped: list[str] = []
    while True:
        user_prompt = render_user_prompt(query, tuple(retained))
        prompt_tokens = provider.count_tokens(SYSTEM_PROMPT, user_prompt)
        if prompt_tokens + config.max_output_tokens <= config.context_tokens:
            return tuple(retained), tuple(dropped), user_prompt, prompt_tokens
        if not retained:
            raise ContextBudgetError("irreducible prompt exceeds configured context budget")
        dropped.append(retained.pop().evidence_id)


class GroundedGenerator:
    def __init__(
        self,
        config: GenerationConfig,
        reranking: RerankingPipeline,
        provider: SLMProvider,
    ) -> None:
        self.config = config
        self.reranking = reranking
        self.provider = provider

    def diagnose(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
    ) -> GenerationOutcome:
        started = perf_counter()
        reranked = self.reranking.rerank_query(query, filters=filters)
        evidence = build_evidence_pack(
            reranked.results,
            limit=self.reranking.config.evidence_k,
        )
        lineage = self._lineage(query, reranked)
        if not evidence:
            return self._insufficient(
                "No retrievable evidence was available for this query.",
                lineage,
                reranked.timings,
                perf_counter() - started,
            )
        return self._synthesize(
            query,
            evidence,
            lineage,
            reranked.timings,
            started,
        )

    def generate_from_evidence(
        self,
        query: str,
        evidence: tuple[EvidenceItem, ...],
        *,
        lineage: dict[str, Any],
    ) -> GenerationOutcome:
        """Exercise the same grounded boundary with an explicit evidence fixture."""
        return self._synthesize(query, evidence, lineage, {}, perf_counter())

    def _synthesize(
        self,
        query: str,
        evidence: tuple[EvidenceItem, ...],
        lineage: dict[str, Any],
        reranking_timings: dict[str, float],
        started: float,
    ) -> GenerationOutcome:
        try:
            retained, dropped, user_prompt, counted_tokens = fit_context(
                query, evidence, self.provider, self.config
            )
        except (ConnectionError, RuntimeError) as exc:
            raise SLMUnavailableError(f"local SLM tokenization failed: {exc}") from exc
        if not retained:
            return self._insufficient(
                "Retrieved evidence could not fit the configured context budget.",
                lineage,
                reranking_timings,
                perf_counter() - started,
                dropped=dropped,
            )
        try:
            generated = self.provider.generate(SYSTEM_PROMPT, user_prompt)
        except (ConnectionError, RuntimeError) as exc:
            raise SLMUnavailableError(f"local SLM generation failed: {exc}") from exc
        response = parse_and_validate(generated.text, retained)
        return GenerationOutcome(
            response=response,
            evidence=retained,
            evidence_dropped_for_context=dropped,
            lineage={
                **lineage,
                "evidence_ids": [item.evidence_id for item in retained],
                "evidence_chunk_ids": [item.chunk_id for item in retained],
            },
            performance={
                **reranking_timings,
                "context_prompt_tokens": counted_tokens,
                "provider_prompt_tokens": generated.prompt_tokens,
                "generated_tokens": generated.generated_tokens,
                "generation_seconds": generated.total_seconds,
                "time_to_first_token_seconds": generated.time_to_first_token_seconds,
                "tokens_per_second": generated.tokens_per_second,
                "end_to_end_seconds": perf_counter() - started,
            },
        )

    def _lineage(self, query: str, reranked: Any) -> dict[str, Any]:
        return {
            "query": query,
            "corpus_fingerprint": reranked.corpus_fingerprint,
            "retrieval_contract": self.reranking.retriever.config.retrieval_contract(),
            "reranking_contract": self.reranking.config.contract(
                self.reranking.retriever.config.retrieval_contract()
            ),
            "retrieval_and_reranking_results": [
                item.to_dict(include_content=False) for item in reranked.results
            ],
            "prompt_version": self.config.prompt_version,
            "slm_contract": self.config.contract(),
        }

    @staticmethod
    def _insufficient(
        summary: str,
        lineage: dict[str, Any],
        reranking_timings: dict[str, float],
        total: float,
        *,
        dropped: tuple[str, ...] = (),
    ) -> GenerationOutcome:
        return GenerationOutcome(
            response=GroundedResponse(
                status="insufficient_evidence",
                summary=summary,
                suspected_causes=[],
                recommended_actions=[],
                citations=[],
            ),
            evidence=(),
            evidence_dropped_for_context=dropped,
            lineage=lineage,
            performance={**reranking_timings, "end_to_end_seconds": total},
        )
