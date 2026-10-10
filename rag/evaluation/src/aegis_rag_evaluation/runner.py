from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from aegis_rag_generation.contracts import EvidenceItem
from aegis_rag_generation.errors import GenerationError
from aegis_rag_generation.evidence import build_evidence_pack
from aegis_rag_generation.generator import GroundedGenerator
from aegis_rag_reranking.errors import RerankingError

from aegis_rag_evaluation.adversarial import apply_overlay
from aegis_rag_evaluation.artifacts import generation_path, write_generation_artifact
from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.contracts import BenchmarkBundle, QueryCase, Split, Variant
from aegis_rag_evaluation.errors import ArtifactGuardError


def generate_split(
    config: EvaluationConfig,
    bundle: BenchmarkBundle,
    split: Split,
    variant: Variant,
    generator: GroundedGenerator,
    *,
    confirm_final: bool = False,
) -> dict[str, Any]:
    path = generation_path(config, bundle, split, variant)
    if split == "final" and not confirm_final:
        raise ArtifactGuardError("final generation requires --confirm-final")
    if split == "final" and path.exists():
        raise ArtifactGuardError(f"final artifact is write-once and already exists: {path}")
    pipeline = generator.reranking
    actual_fingerprint = pipeline.retriever.snapshot.fingerprint
    frozen = json.loads(config.pipeline_config_path.read_text(encoding="utf-8"))
    expected_fingerprint = frozen["corpus"]["fingerprint"]
    if actual_fingerprint != expected_fingerprint:
        raise ValueError(
            "corpus fingerprint mismatch: "
            f"expected {expected_fingerprint}, got {actual_fingerprint}"
        )
    cases = []
    started = perf_counter()
    for case in bundle.selected(split, variant):
        cases.append(_generate_case(case, variant, bundle, generator))
    artifact = {
        "artifact_version": 1,
        "benchmark_id": bundle.benchmark_id,
        "query_hash": bundle.query_hash,
        "pipeline_config_hash": bundle.pipeline_hash,
        "corpus_fingerprint": actual_fingerprint,
        "split": split,
        "variant": variant,
        "case_count": len(cases),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": perf_counter() - started,
        "cases": cases,
    }
    write_generation_artifact(path, artifact, split=split, confirm_final=confirm_final)
    return {"path": str(path), **{key: artifact[key] for key in (
        "benchmark_id", "split", "variant", "case_count", "duration_seconds"
    )}}


def _generate_case(
    case: QueryCase,
    variant: Variant,
    bundle: BenchmarkBundle,
    generator: GroundedGenerator,
) -> dict[str, Any]:
    case_started = perf_counter()
    retrieved: list[dict[str, object]] = []
    reranked: list[dict[str, object]] = []
    evidence: tuple[EvidenceItem, ...] = ()
    timings: dict[str, float] = {}
    try:
        if variant == "canonical":
            run = generator.reranking.rerank_query(case.query)
            retrieved = [item.to_dict(include_content=False) for item in run.candidates]
            reranked = [item.to_dict(include_content=False) for item in run.results]
            evidence = build_evidence_pack(
                run.results, limit=generator.reranking.config.evidence_k
            )
            timings = run.timings
        else:
            branches = generator.reranking.retriever.retrieve_branches(case.query)
            retrieved = [item.to_dict(include_content=False) for item in branches.hybrid]
            evidence = tuple(
                EvidenceItem(
                    evidence_id=f"E{rank}",
                    chunk_id=hit.chunk.chunk_id,
                    source_path=hit.chunk.source_path,
                    title=hit.chunk.title,
                    heading_path=hit.chunk.heading_path,
                    content=hit.chunk.content,
                    reranked_rank=rank,
                )
                for rank, hit in enumerate(branches.hybrid[:5], 1)
            )
            timings = {f"retrieval_{key}": value for key, value in branches.timings.items()}
        if case.case_type == "adversarial":
            evidence = _overlay_evidence(evidence, bundle.overlays[case.case_id])
        lineage = {
            "query": case.query,
            "corpus_fingerprint": generator.reranking.retriever.snapshot.fingerprint,
            "retrieval_contract": generator.reranking.retriever.config.retrieval_contract(),
            "reranking_contract": generator.reranking.config.contract(
                generator.reranking.retriever.config.retrieval_contract()
            ),
            "variant": variant,
            "prompt_version": generator.config.prompt_version,
            "slm_contract": generator.config.contract(),
        }
        outcome = generator.generate_from_evidence(case.query, evidence, lineage=lineage)
        response = outcome.response.model_dump()
        performance = {**timings, **outcome.performance}
        error = None
        final_evidence = outcome.evidence
    except (GenerationError, RerankingError, ValueError, OSError) as exc:
        response = None
        performance = {**timings, "end_to_end_seconds": perf_counter() - case_started}
        error = {"type": type(exc).__name__, "message": str(exc)}
        final_evidence = evidence
    return {
        "case_id": case.case_id,
        "expected_status": bundle.gold[case.case_id].expected_status,
        "split": case.split,
        "variant": variant,
        "query": case.query,
        "corpus_fingerprint": generator.reranking.retriever.snapshot.fingerprint,
        "retrieval_configuration_hash": bundle.pipeline_hash,
        "retrieved_results": retrieved,
        "reranked_results": reranked,
        "evidence": [_evidence_dict(item) for item in final_evidence],
        "evidence_ids": [item.evidence_id for item in final_evidence],
        "prompt_version": generator.config.prompt_version,
        "qwen_model": generator.config.contract()["model"],
        "generation_parameters": generator.config.contract()["generation"],
        "structured_response": response,
        "generation_timing": performance,
        "prompt_tokens": performance.get("provider_prompt_tokens"),
        "output_tokens": performance.get("generated_tokens"),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "error": error,
    }


def _overlay_evidence(evidence, overlay):
    values = []
    for index, item in enumerate(evidence, 1):
        if index == overlay.target_evidence_rank:
            item = EvidenceItem(
                evidence_id=item.evidence_id,
                chunk_id=item.chunk_id,
                source_path=item.source_path,
                title=item.title,
                heading_path=item.heading_path,
                content=apply_overlay(item.content, overlay),
                reranked_rank=item.reranked_rank,
            )
        values.append(item)
    return tuple(values)


def _evidence_dict(item: EvidenceItem) -> dict[str, object]:
    return {
        "evidence_id": item.evidence_id,
        "chunk_id": item.chunk_id,
        "source_path": item.source_path,
        "title": item.title,
        "heading_path": list(item.heading_path),
        "content": item.content,
        "rank": item.reranked_rank,
    }
