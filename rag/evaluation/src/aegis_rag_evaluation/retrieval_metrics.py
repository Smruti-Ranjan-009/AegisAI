from __future__ import annotations

import math
from collections.abc import Iterable

from aegis_rag_evaluation.contracts import GoldRecord
from aegis_rag_evaluation.gold import section_key


def case_retrieval_metrics(
    results: list[dict[str, object]], gold: GoldRecord
) -> dict[str, float]:
    relevant = {section.key: section.grade for section in gold.relevant_sections}
    ranked = [section_key(item) for item in results]
    values: dict[str, float] = {}
    for cutoff in (1, 3, 5):
        hits = sum(key in relevant for key in set(ranked[:cutoff]))
        values[f"recall@{cutoff}"] = hits / len(relevant) if relevant else 0.0
        values[f"hit@{cutoff}"] = float(hits > 0)
    first = next((rank for rank, key in enumerate(ranked[:5], 1) if key in relevant), None)
    values["mrr@5"] = 1.0 / first if first else 0.0
    gains = [relevant.get(key, 0) for key in ranked[:5]]
    dcg = _dcg(gains)
    ideal = _dcg(sorted(relevant.values(), reverse=True)[:5])
    values["ndcg@5"] = dcg / ideal if ideal else 0.0
    return values


def _dcg(grades: Iterable[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]}
