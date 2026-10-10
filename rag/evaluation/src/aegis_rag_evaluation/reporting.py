from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.contracts import BenchmarkBundle, Split
from aegis_rag_evaluation.statistics import bootstrap_interval, paired_bootstrap_difference


def create_reports(
    config: EvaluationConfig,
    bundle: BenchmarkBundle,
    split: Split,
    canonical: dict[str, Any],
    ablation: dict[str, Any] | None = None,
) -> dict[str, str]:
    output = config.runtime_root / bundle.benchmark_id / "reports" / split
    output.mkdir(parents=True, exist_ok=True)
    comparison = _comparison(canonical, ablation) if ablation else None
    summary = {
        "benchmark_id": bundle.benchmark_id,
        "split": split,
        "canonical": {
            "metrics": canonical["metrics"],
            "retrieval": canonical["retrieval"],
            "abstention": canonical["abstention"],
            "adversarial": canonical["adversarial"],
            "generation_performance": canonical["generation_performance"],
            "evaluation_performance": canonical["evaluation_performance"],
        },
        "paired_ablation": comparison,
        "by_incident_family": canonical["by_incident_family"],
        "by_query_style": canonical["by_query_style"],
        "failure_analysis": canonical["failure_analysis"],
        "limitations": _limitations(),
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = output / "summary.md"
    markdown_path.write_text(_markdown(summary), encoding="utf-8")
    case_path = output / "case-report.json"
    case_path.write_text(
        json.dumps({"benchmark_id": bundle.benchmark_id, "cases": canonical["cases"]}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    review_path = output / "manual-review.csv"
    _manual_review(review_path, canonical["cases"])
    return {
        "summary_json": str(summary_path),
        "summary_markdown": str(markdown_path),
        "case_report": str(case_path),
        "manual_review": str(review_path),
    }


def _comparison(canonical, ablation):
    canonical_cases = {
        row["case_id"]: row
        for row in canonical["cases"]
        if row["case_type"] == "grounded" and row["claim_support"]
    }
    ablation_cases = {
        row["case_id"]: row
        for row in ablation["cases"]
        if row["case_type"] == "grounded" and row["claim_support"]
    }
    ids = sorted(set(canonical_cases) & set(ablation_cases))
    extractors = {
        "gold_citation_precision": lambda row: row["citation_gold"]["precision"],
        "gold_citation_recall": lambda row: row["citation_gold"]["recall"],
        "nli_supported_claim_rate": lambda row: row["claim_support"][
            "nli_supported_claim_rate"
        ]
        or 0.0,
        "nli_expected_fact_coverage": lambda row: row["completeness"][
            "nli_expected_fact_coverage"
        ]
        or 0.0,
        "query_answer_semantic_similarity": lambda row: row[
            "query_answer_semantic_similarity"
        ]
        or 0.0,
        "end_to_end_seconds": lambda row: row["latency"].get("end_to_end_seconds", 0.0),
    }
    metrics = {}
    for name, extractor in extractors.items():
        left = [extractor(canonical_cases[case_id]) for case_id in ids]
        right = [extractor(ablation_cases[case_id]) for case_id in ids]
        metrics[name] = {
            "canonical": bootstrap_interval(left),
            "ablation": bootstrap_interval(right),
            "paired_delta_canonical_minus_ablation": paired_bootstrap_difference(left, right),
        }
    return {"matched_grounded_cases": len(ids), "metrics": metrics}


def _manual_review(path: Path, cases: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "query",
        "response_summary",
        "expected_status",
        "human_groundedness",
        "human_correctness",
        "human_relevance",
        "human_citation_quality",
        "human_notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "query": case["query"],
                    "response_summary": case.get("response_summary", ""),
                    "expected_status": case["expected_status"],
                    "human_groundedness": "",
                    "human_correctness": "",
                    "human_relevance": "",
                    "human_citation_quality": "",
                    "human_notes": "",
                }
            )


def _markdown(summary: dict[str, Any]) -> str:
    metrics = summary["canonical"]["metrics"]
    retrieval = summary["canonical"]["retrieval"]
    abstention = summary["canonical"]["abstention"]
    adversarial = summary["canonical"]["adversarial"]
    lines = [
        f"# Phase 11 {summary['split'].title()} Evaluation",
        "",
        f"Benchmark: `{summary['benchmark_id']}`",
        "",
        "## Headline metrics",
        "",
        f"- NLI-supported claims: {metrics['nli_supported_claims']} / {metrics['claims']} "
        f"({_percent(metrics['nli_supported_claim_rate'])})",
        f"- Unsupported claims: {metrics['unsupported_claims']} / {metrics['claims']} "
        f"({_percent(metrics['unsupported_claim_rate'])})",
        f"- Gold citation precision: {_percent(metrics['gold_citation_precision'])}",
        f"- Gold citation recall: {_percent(metrics['gold_citation_recall'])}",
        f"- NLI expected-fact coverage: {metrics['covered_facts']} / {metrics['required_facts']} "
        f"({_percent(metrics['nli_expected_fact_coverage'])})",
        "- Unsupported-query abstention: "
        f"{_percent(abstention['unsupported_query_abstention_rate'])}",
        f"- Adversarial pass rate: {adversarial['passed']} / {adversarial['cases']} "
        f"({_percent(adversarial['prompt_injection_pass_rate'])})",
        "- Reranked NDCG@5: "
        f"{_number((retrieval['hybrid_rrf_plus_cross_encoder'] or {}).get('ndcg@5'))}",
        "",
        "## Interpretation",
        "",
        "NLI values are automated semantic proxies, not human-verified factual correctness. "
        "Citation recall does not require every potentially useful source for an answer "
        "to be usable. Final percentiles and bootstrap intervals are descriptive for "
        "this small curated benchmark.",
        "",
        "## Failure analysis",
        "",
    ]
    for category, count in summary["failure_analysis"]["counts"].items():
        lines.append(f"- {category}: {count}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def _limitations() -> list[str]:
    return [
        "The corpus contains only 15 documents and 65 chunks and is mostly synthetic.",
        "The final split contains only 15 cases and its gold judgments are manually curated.",
        "DeBERTa NLI is an imperfect automated proxy, not human evaluation.",
        "The benchmark and models are English-only.",
        "Generation uses one local quantized Qwen3-4B model on one machine.",
        "Latency percentiles are descriptive at this sample size.",
        "Human review is not claimed unless the separate template is completed later.",
        "No production user traffic is represented.",
    ]


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
