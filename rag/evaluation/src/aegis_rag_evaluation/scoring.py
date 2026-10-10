from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import numpy as np

from aegis_rag_evaluation.abstention import abstention_metrics
from aegis_rag_evaluation.adversarial import adversarial_result
from aegis_rag_evaluation.artifacts import (
    generation_path,
    load_generation_artifact,
    score_path,
    write_score_artifact,
)
from aegis_rag_evaluation.citation_metrics import (
    gold_citation_metrics,
    structural_citation_validity,
)
from aegis_rag_evaluation.claim_support import evaluate_claim_support
from aegis_rag_evaluation.completeness import evaluate_completeness
from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.contracts import BenchmarkBundle, NLIProvider, Split, Variant
from aegis_rag_evaluation.relevance import query_answer_similarity
from aegis_rag_evaluation.retrieval_metrics import case_retrieval_metrics


def score_split(
    config: EvaluationConfig,
    bundle: BenchmarkBundle,
    split: Split,
    variant: Variant,
    nli: NLIProvider,
    embeddings,
) -> dict[str, Any]:
    artifact = load_generation_artifact(
        generation_path(config, bundle, split, variant),
        bundle=bundle,
        config=config,
        split=split,
        variant=variant,
    )
    by_id = {case.case_id: case for case in bundle.cases}
    started = perf_counter()
    scored = []
    for generated in artifact["cases"]:
        case = by_id[generated["case_id"]]
        gold = bundle.gold[case.case_id]
        scored.append(_score_case(generated, case, gold, bundle, nli, embeddings))
    evaluation_seconds = perf_counter() - started
    report = {
        "report_version": 1,
        "benchmark_id": bundle.benchmark_id,
        "split": split,
        "variant": variant,
        "query_hash": bundle.query_hash,
        "gold_hash": bundle.gold_hash,
        "overlay_hash": bundle.overlay_hash,
        "pipeline_config_hash": bundle.pipeline_hash,
        "evaluator_config_hash": bundle.evaluator_hash,
        "corpus_fingerprint": artifact["corpus_fingerprint"],
        "scored_at_utc": datetime.now(UTC).isoformat(),
        "metrics": _aggregate(scored),
        "retrieval": _retrieval_aggregate(scored),
        "abstention": _abstention(scored),
        "adversarial": _adversarial(scored),
        "by_incident_family": _groups(scored, "incident_family"),
        "by_query_style": _groups(scored, "query_style"),
        "failure_analysis": _failures(scored),
        "generation_performance": _performance(scored),
        "evaluation_performance": {
            "nli_model": nli.model_id,
            "nli_revision": nli.model_revision,
            "nli_load_seconds": nli.load_seconds,
            "evaluation_seconds": evaluation_seconds,
            "pairs_scored": sum(_nli_pair_count(row) for row in scored),
            "claims_scored": sum(
                row["claim_support"]["claim_count"]
                for row in scored
                if row["claim_support"]
            ),
            "facts_scored": sum(
                row["completeness"]["fact_count"]
                for row in scored
                if row["completeness"] and not row["completeness"]["excluded"]
            ),
            "actions_scored": sum(
                row["completeness"]["action_count"]
                for row in scored
                if row["completeness"] and not row["completeness"]["excluded"]
            ),
            "nli_inference_seconds": getattr(nli, "inference_seconds", None),
            "nli_truncated_pairs": _truncated_pairs(scored),
        },
        "cases": scored,
    }
    pairs = report["evaluation_performance"]["pairs_scored"]
    report["evaluation_performance"]["pairs_per_second"] = (
        pairs / evaluation_seconds if evaluation_seconds else None
    )
    inference_seconds = report["evaluation_performance"]["nli_inference_seconds"]
    report["evaluation_performance"]["nli_pairs_per_second"] = (
        pairs / inference_seconds if inference_seconds else None
    )
    write_score_artifact(score_path(config, bundle, split, variant), report)
    return report


def _score_case(generated, case, gold, bundle, nli, embeddings):
    failures: list[str] = []
    retrieval = None
    reranking = None
    if case.case_type == "grounded":
        retrieval = case_retrieval_metrics(generated["retrieved_results"], gold)
        if generated["reranked_results"]:
            reranking = case_retrieval_metrics(generated["reranked_results"], gold)
        if retrieval["hit@5"] == 0:
            failures.append("retrieval_miss")
        if reranking and reranking["ndcg@5"] < retrieval["ndcg@5"]:
            failures.append("reranking_regression")
    if generated.get("error") or generated.get("structured_response") is None:
        error_type = (generated.get("error") or {}).get("type")
        failure = (
            "schema_failure"
            if error_type == "GenerationValidationError"
            else "generation_failure"
        )
        failures.append(failure)
        adversarial = None
        if case.case_type == "adversarial":
            adversarial = {"passed": False, "failure_reasons": [failure]}
            failures.append("prompt_injection_failure")
        return {
            "case_id": case.case_id,
            "query": case.query,
            "case_type": case.case_type,
            "incident_family": case.incident_family,
            "query_style": case.query_style,
            "expected_status": gold.expected_status,
            "observed_status": None,
            "generation_error": generated.get("error"),
            "retrieval": retrieval,
            "reranking": reranking,
            "citation_structural": {"valid": False, "reasons": ["generation_failure"]},
            "citation_gold": None,
            "claim_support": None,
            "completeness": None,
            "query_answer_semantic_similarity": None,
            "adversarial": adversarial,
            "latency": generated.get("generation_timing", {}),
            "failure_categories": sorted(set(failures)),
        }
    response = generated["structured_response"]
    observed = response["status"]
    structural = structural_citation_validity(generated)
    citations = gold_citation_metrics(response["citations"], gold)
    support = evaluate_claim_support(generated, nli)
    completeness = evaluate_completeness(generated, gold, nli)
    similarity = query_answer_similarity(case.query, response, embeddings)
    if observed != gold.expected_status:
        failures.append(
            "false_abstention"
            if observed == "insufficient_evidence"
            else "false_grounded_answer"
        )
    if not structural["valid"]:
        failures.append("incorrect_citation")
    if support["unsupported_claim_rate"]:
        failures.append("unsupported_claim")
    if completeness["nli_expected_fact_coverage"] is not None and completeness[
        "nli_expected_fact_coverage"
    ] < 1:
        failures.append("missing_gold_fact")
    adversarial = None
    if case.case_type == "adversarial":
        adversarial = adversarial_result(
            generated,
            bundle.overlays[case.case_id],
            expected_status=gold.expected_status,
            claims_supported=support["unsupported_claim_rate"] == 0,
        )
        if not adversarial["passed"]:
            failures.append("prompt_injection_failure")
    return {
        "case_id": case.case_id,
        "query": case.query,
        "case_type": case.case_type,
        "incident_family": case.incident_family,
        "query_style": case.query_style,
        "expected_status": gold.expected_status,
        "observed_status": observed,
        "generation_error": None,
        "gold_evidence": [section.model_dump() for section in gold.relevant_sections],
        "retrieved_evidence": generated["retrieved_results"],
        "reranked_evidence": generated["reranked_results"],
        "citations": response["citations"],
        "retrieval": retrieval,
        "reranking": reranking,
        "citation_structural": structural,
        "citation_gold": citations,
        "claim_support": support,
        "completeness": completeness,
        "query_answer_semantic_similarity": similarity,
        "adversarial": adversarial,
        "latency": generated["generation_timing"],
        "response_summary": response["summary"],
        "failure_categories": sorted(set(failures)),
    }


def _aggregate(rows):
    usable = [row for row in rows if row["claim_support"] is not None]
    claims = sum(row["claim_support"]["claim_count"] for row in usable)
    supported = sum(row["claim_support"]["supported_claims"] for row in usable)
    contradicted = sum(row["claim_support"]["contradicted_claims"] for row in usable)
    neutral = sum(row["claim_support"]["neutral_claims"] for row in usable)
    citation_rows = [row["citation_gold"] for row in usable if row["citation_gold"]]
    cited = sum(row["cited_sections"] for row in citation_rows)
    all_gold = sum(row["all_relevant_sections"] for row in citation_rows)
    direct_gold = sum(row["direct_sections"] for row in citation_rows)
    all_hits = sum(row["all_relevant_hits"] for row in citation_rows)
    direct_hits = sum(row["direct_hits"] for row in citation_rows)
    fact_rows = [row["completeness"] for row in usable if not row["completeness"]["excluded"]]
    facts = sum(row["fact_count"] for row in fact_rows)
    covered_facts = sum(row["covered_facts"] for row in fact_rows)
    actions = sum(row["action_count"] for row in fact_rows)
    covered_actions = sum(row["covered_actions"] for row in fact_rows)
    similarities = [
        row["query_answer_semantic_similarity"]
        for row in usable
        if row["query_answer_semantic_similarity"] is not None
    ]
    summaries = [
        row["claim_support"]["summary_support_proxy"]
        for row in usable
        if row["claim_support"]["summary_support_proxy"] is not None
    ]
    supported_summaries = sum(row["label"] == "entailment" for row in summaries)
    return {
        "claims": claims,
        "nli_supported_claims": supported,
        "nli_supported_claim_rate": supported / claims if claims else None,
        "unsupported_claims": claims - supported,
        "unsupported_claim_rate": (claims - supported) / claims if claims else None,
        "contradicted_claims": contradicted,
        "contradiction_rate": contradicted / claims if claims else None,
        "neutral_claims": neutral,
        "neutral_rate": neutral / claims if claims else None,
        "nli_supported_summaries": supported_summaries,
        "summary_support_proxy_count": len(summaries),
        "nli_summary_support_proxy_rate": supported_summaries / len(summaries)
        if summaries
        else None,
        "citation_structural_valid_cases": sum(
            row["citation_structural"]["valid"] for row in rows
        ),
        "citation_structural_cases": len(rows),
        "citation_structural_validity_rate": sum(
            row["citation_structural"]["valid"] for row in rows
        )
        / len(rows)
        if rows
        else None,
        "gold_citation_precision": all_hits / cited if cited else 0.0,
        "gold_citation_recall": all_hits / all_gold if all_gold else 0.0,
        "direct_citation_precision": direct_hits / cited if cited else 0.0,
        "direct_citation_recall": direct_hits / direct_gold if direct_gold else 0.0,
        "covered_facts": covered_facts,
        "required_facts": facts,
        "nli_expected_fact_coverage": covered_facts / facts if facts else None,
        "covered_reference_actions": covered_actions,
        "reference_actions": actions,
        "reference_action_coverage": covered_actions / actions if actions else None,
        "query_answer_semantic_similarity": _distribution(similarities),
    }


def _retrieval_aggregate(rows):
    grounded = [row for row in rows if row["case_type"] == "grounded" and row["retrieval"]]
    return {
        "grounded_cases": len(grounded),
        "hybrid_rrf": _mean_metric(grounded, "retrieval"),
        "hybrid_rrf_plus_cross_encoder": _mean_metric(grounded, "reranking"),
    }


def _mean_metric(rows, field):
    selected = [row[field] for row in rows if row[field]]
    if not selected:
        return None
    return {key: sum(item[key] for item in selected) / len(selected) for key in selected[0]}


def _abstention(rows):
    selected = [
        row
        for row in rows
        if row["case_type"] != "adversarial" and row["observed_status"]
    ]
    return abstention_metrics(
        [(row["expected_status"], row["observed_status"]) for row in selected]
    )


def _adversarial(rows):
    selected = [row for row in rows if row["adversarial"] is not None]
    passed = sum(row["adversarial"]["passed"] for row in selected)
    return {
        "passed": passed,
        "cases": len(selected),
        "prompt_injection_pass_rate": passed / len(selected) if selected else None,
    }


def _groups(rows, field):
    groups = defaultdict(list)
    for row in rows:
        if row["case_type"] == "grounded" and row[field]:
            groups[row[field]].append(row)
    return {
        name: {
            "cases": len(values),
            "hybrid_rrf_ndcg@5": _metric_mean(values, "retrieval", "ndcg@5"),
            "reranked_ndcg@5": _metric_mean(values, "reranking", "ndcg@5"),
            **_aggregate(values),
        }
        for name, values in sorted(groups.items())
    }


def _metric_mean(rows, field, metric):
    values = [row[field][metric] for row in rows if row[field]]
    return sum(values) / len(values) if values else None


def _failures(rows):
    counts = defaultdict(int)
    cases = []
    for row in rows:
        for category in row["failure_categories"]:
            counts[category] += 1
        if row["failure_categories"]:
            cases.append({"case_id": row["case_id"], "categories": row["failure_categories"]})
    return {"counts": dict(sorted(counts.items())), "cases": cases}


def _performance(rows):
    keys = {
        "retrieval": "retrieval_total_seconds",
        "reranking": "reranker_seconds",
        "generation": "generation_seconds",
        "total": "end_to_end_seconds",
        "prompt_tokens": "provider_prompt_tokens",
        "output_tokens": "generated_tokens",
        "tokens_per_second": "tokens_per_second",
    }
    return {
        name: _distribution(
            [float(row["latency"][key]) for row in rows if row["latency"].get(key) is not None]
        )
        for name, key in keys.items()
    }


def _distribution(values):
    if not values:
        return None
    data = np.asarray(values, dtype=float)
    return {
        "count": len(values),
        "mean": float(np.mean(data)),
        "median": float(np.median(data)),
        "p50": float(np.percentile(data, 50)),
        "p95": float(np.percentile(data, 95)),
        "p99": float(np.percentile(data, 99)),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
    }


def _nli_pair_count(row):
    if not row["claim_support"]:
        return 0
    support = row["claim_support"]
    completeness = row["completeness"]
    return (
        support["claim_count"]
        + int(support["summary_support_proxy"] is not None)
        + len(completeness["facts"])
        + len(completeness["actions"])
    )


def _truncated_pairs(rows):
    count = 0
    for row in rows:
        if not row["claim_support"]:
            continue
        support = row["claim_support"]
        count += sum(claim["truncated"] for claim in support["claims"])
        if support["summary_support_proxy"]:
            count += support["summary_support_proxy"]["truncated"]
        completeness = row["completeness"]
        count += sum(item["truncated"] for item in completeness["facts"])
        count += sum(item["truncated"] for item in completeness["actions"])
    return count
