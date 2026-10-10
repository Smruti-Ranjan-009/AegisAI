from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.contracts import BenchmarkBundle
from aegis_rag_evaluation.runner import _generate_case

DEFAULT_CASES = ("e2e-g-001", "e2e-g-007", "e2e-g-013", "e2e-g-019", "e2e-g-025")


def run_determinism_check(
    config: EvaluationConfig,
    bundle: BenchmarkBundle,
    generator,
    case_ids: tuple[str, ...] = DEFAULT_CASES,
) -> dict[str, Any]:
    by_id = {case.case_id: case for case in bundle.cases}
    rows = []
    for case_id in case_ids:
        case = by_id[case_id]
        first = _generate_case(case, "canonical", bundle, generator)
        second = _generate_case(case, "canonical", bundle, generator)
        checks = {
            "retrieval_ranking": _ids(first["retrieved_results"])
            == _ids(second["retrieved_results"]),
            "reranking": _ids(first["reranked_results"]) == _ids(second["reranked_results"]),
            "evidence_ids": first["evidence_ids"] == second["evidence_ids"],
            "structured_json": _normalized(first["structured_response"])
            == _normalized(second["structured_response"]),
            "citation_set": _citations(first["structured_response"])
            == _citations(second["structured_response"]),
        }
        rows.append({"case_id": case_id, "checks": checks, "exact": all(checks.values())})
    report = {
        "benchmark_id": bundle.benchmark_id,
        "case_count": len(rows),
        "exact_cases": sum(row["exact"] for row in rows),
        "exact_structured_output_agreement_rate": sum(
            row["checks"]["structured_json"] for row in rows
        )
        / len(rows),
        "all_contract_agreement_rate": sum(row["exact"] for row in rows) / len(rows),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "cases": rows,
    }
    path = config.runtime_root / bundle.benchmark_id / "reports" / "determinism.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), **report}


def _ids(results):
    return [item["chunk_id"] for item in results]


def _normalized(response):
    return json.dumps(response, sort_keys=True, separators=(",", ":"))


def _citations(response):
    if not response:
        return None
    return sorted(
        (item["evidence_id"], item["source_path"], tuple(item["heading_path"]))
        for item in response["citations"]
    )
