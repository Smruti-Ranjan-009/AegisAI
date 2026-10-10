from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from aegis_rag_evaluation.config import EvaluationConfig, canonical_hash, sha256_file
from aegis_rag_evaluation.contracts import (
    AdversarialOverlay,
    BenchmarkBundle,
    GoldRecord,
    QueryCase,
)
from aegis_rag_evaluation.errors import BenchmarkValidationError

FAMILIES = (
    "cpu_saturation",
    "memory_leak",
    "service_failure",
    "dependency_failure",
    "high_latency",
)
STYLES = ("symptom", "signal", "root_cause", "mitigation", "operational_dependency")
METRIC_DEFINITIONS = {
    "retrieval": ["recall@1/3/5", "hit@1/3/5", "mrr@5", "ndcg@5"],
    "citation": ["structural", "gold_all_precision_recall", "gold_direct_precision_recall"],
    "semantic": ["nli_claim_support", "nli_fact_coverage", "reference_action_coverage"],
    "status": ["abstention_confusion", "adversarial_pass"],
    "relevance": "bge_query_answer_cosine",
    "version": "e2e-rag-metrics-v1",
}


def _load_jsonl(path: Path, model):
    values = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                values.append(model.model_validate_json(line))
    except (OSError, ValueError) as exc:
        raise BenchmarkValidationError(f"invalid {path.name}: {exc}") from exc
    if not values:
        raise BenchmarkValidationError(f"{path.name} is empty")
    return tuple(values)


def load_benchmark(config: EvaluationConfig) -> BenchmarkBundle:
    query_path = config.evaluation_root / "e2e_queries_v1.jsonl"
    gold_path = config.evaluation_root / "e2e_gold_v1.jsonl"
    overlay_path = config.evaluation_root / "adversarial_overlays_v1.jsonl"
    cases = _load_jsonl(query_path, QueryCase)
    gold_values = _load_jsonl(gold_path, GoldRecord)
    overlay_values = _load_jsonl(overlay_path, AdversarialOverlay)
    gold = _unique_map(gold_values, "gold")
    overlays = _unique_map(overlay_values, "overlay")
    query_hash = sha256_file(query_path)
    gold_hash = sha256_file(gold_path)
    overlay_hash = sha256_file(overlay_path)
    identity = {
        "corpus_fingerprint": json.loads(config.pipeline_config_path.read_text())["corpus"][
            "fingerprint"
        ],
        "evaluator_hash": config.evaluator_hash,
        "gold_hash": gold_hash,
        "metric_definitions": METRIC_DEFINITIONS,
        "overlay_hash": overlay_hash,
        "pipeline_hash": config.pipeline_hash,
        "query_hash": query_hash,
    }
    bundle = BenchmarkBundle(
        cases=cases,
        gold=gold,
        overlays=overlays,
        query_hash=query_hash,
        gold_hash=gold_hash,
        overlay_hash=overlay_hash,
        pipeline_hash=config.pipeline_hash,
        evaluator_hash=config.evaluator_hash,
        benchmark_id=f"e2e-rag-v1-{canonical_hash(identity)[:12]}",
    )
    validate_benchmark(bundle, config.repository / "rag" / "knowledge")
    return bundle


def _unique_map(values, label: str):
    result = {value.case_id: value for value in values}
    if len(result) != len(values):
        raise BenchmarkValidationError(f"duplicate {label} case_id")
    return result


def validate_benchmark(bundle: BenchmarkBundle, corpus_root: Path) -> None:
    if len(bundle.cases) != 40:
        raise BenchmarkValidationError("benchmark must contain exactly 40 cases")
    ids = [case.case_id for case in bundle.cases]
    if len(set(ids)) != len(ids):
        raise BenchmarkValidationError("query case_id values must be unique")
    if set(ids) != set(bundle.gold):
        raise BenchmarkValidationError("query and gold case IDs must match exactly")
    type_counts = Counter(case.case_type for case in bundle.cases)
    if type_counts != {"grounded": 30, "insufficient": 5, "adversarial": 5}:
        raise BenchmarkValidationError(f"invalid case composition: {dict(type_counts)}")
    split_counts = Counter(case.split for case in bundle.cases)
    if split_counts != {"development": 25, "final": 15}:
        raise BenchmarkValidationError(f"invalid split: {dict(split_counts)}")
    expected_by_split = {
        "development": {"grounded": 20, "insufficient": 3, "adversarial": 2},
        "final": {"grounded": 10, "insufficient": 2, "adversarial": 3},
    }
    for split, expected in expected_by_split.items():
        actual = Counter(case.case_type for case in bundle.cases if case.split == split)
        if actual != expected:
            raise BenchmarkValidationError(f"invalid {split} composition: {dict(actual)}")
    grounded = [case for case in bundle.cases if case.case_type == "grounded"]
    _require_balance(grounded, 6, "full grounded")
    final_grounded = [case for case in grounded if case.split == "final"]
    _require_balance(final_grounded, 2, "final grounded")
    adversarial_ids = {case.case_id for case in bundle.cases if case.case_type == "adversarial"}
    if set(bundle.overlays) != adversarial_ids:
        raise BenchmarkValidationError("overlays must match adversarial cases exactly")
    corpus_sections = _corpus_sections(corpus_root)
    for case in bundle.cases:
        record = bundle.gold[case.case_id]
        insufficient = case.case_type == "insufficient"
        if insufficient != (record.expected_status == "insufficient_evidence"):
            raise BenchmarkValidationError(f"{case.case_id}: expected status contradicts type")
        if insufficient:
            if record.relevant_sections or record.required_facts or record.acceptable_actions:
                raise BenchmarkValidationError(
                    f"{case.case_id}: insufficient case has gold content"
                )
            continue
        if (
            not record.relevant_sections
            or not record.required_facts
            or not record.acceptable_actions
        ):
            raise BenchmarkValidationError(f"{case.case_id}: grounded gold must be complete")
        if not any(section.grade == 2 for section in record.relevant_sections):
            raise BenchmarkValidationError(f"{case.case_id}: direct evidence is missing")
        for section in record.relevant_sections:
            if section.key not in corpus_sections:
                raise BenchmarkValidationError(
                    f"{case.case_id}: unresolved section {section.source_path} "
                    f"{section.heading_path}"
                )
        for statement in (*record.required_facts, *record.acceptable_actions):
            if len(statement.split()) < 3 or "\n" in statement:
                raise BenchmarkValidationError(f"{case.case_id}: gold statement is not atomic")
    _validate_query_independence(bundle.cases, corpus_root)


def _require_balance(cases: list[QueryCase], expected: int, label: str) -> None:
    families = Counter(case.incident_family for case in cases)
    styles = Counter(case.query_style for case in cases)
    if families != {family: expected for family in FAMILIES}:
        raise BenchmarkValidationError(f"{label} family imbalance: {dict(families)}")
    if styles != {style: expected for style in STYLES}:
        raise BenchmarkValidationError(f"{label} style imbalance: {dict(styles)}")


def _corpus_sections(corpus_root: Path) -> set[tuple[str, tuple[str, ...]]]:
    sections: set[tuple[str, tuple[str, ...]]] = set()
    for path in corpus_root.rglob("*.md"):
        relative = path.relative_to(corpus_root).as_posix()
        headings: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if not match:
                continue
            level = len(match.group(1))
            headings = headings[: level - 1]
            headings.append(match.group(2))
            sections.add((relative, tuple(headings)))
    return sections


def _validate_query_independence(cases: tuple[QueryCase, ...], corpus_root: Path) -> None:
    evaluation_root = corpus_root.parent / "evaluation"
    previous: set[str] = set()
    for name in ("retrieval_queries_v1.jsonl", "reranking_queries_v1.jsonl"):
        for line in (evaluation_root / name).read_text(encoding="utf-8").splitlines():
            previous.add(json.loads(line)["query"].strip().casefold())
    overlap = [case.case_id for case in cases if case.query.strip().casefold() in previous]
    if overlap:
        raise BenchmarkValidationError(f"queries reuse historical text: {overlap}")


def manifest(bundle: BenchmarkBundle, config: EvaluationConfig) -> dict[str, object]:
    pipeline = json.loads(config.pipeline_config_path.read_text(encoding="utf-8"))
    return {
        "benchmark_id": bundle.benchmark_id,
        "counts": {kind: sum(case.case_type == kind for case in bundle.cases) for kind in (
            "grounded", "insufficient", "adversarial"
        )},
        "splits": {split: sum(case.split == split for case in bundle.cases) for split in (
            "development", "final"
        )},
        "query_hash": bundle.query_hash,
        "gold_hash": bundle.gold_hash,
        "overlay_hash": bundle.overlay_hash,
        "pipeline_hash": bundle.pipeline_hash,
        "evaluator_hash": bundle.evaluator_hash,
        "corpus_fingerprint": pipeline["corpus"]["fingerprint"],
        "metric_definitions_hash": canonical_hash(METRIC_DEFINITIONS),
    }
