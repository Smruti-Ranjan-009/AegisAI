from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from statistics import mean
from typing import Any

KS = (1, 3, 5, 10)


def query_metrics(ranked_ids: list[str], grades: dict[str, int]) -> dict[str, float]:
    relevant = set(grades)
    values: dict[str, float] = {}
    for k in KS:
        hits = len(relevant & set(ranked_ids[:k]))
        values[f"recall@{k}"] = hits / len(relevant)
        values[f"hit@{k}"] = float(hits > 0)
    first = next(
        (rank for rank, item in enumerate(ranked_ids[:10], start=1) if item in relevant),
        0,
    )
    values["mrr@10"] = 1.0 / first if first else 0.0
    for k in (5, 10):
        gains = [grades.get(item, 0) for item in ranked_ids[:k]]
        dcg = sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(gains, 1))
        ideal = sorted(grades.values(), reverse=True)[:k]
        idcg = sum(
            (2**grade - 1) / math.log2(rank + 1)
            for rank, grade in enumerate(ideal, 1)
        )
        values[f"ndcg@{k}"] = dcg / idcg if idcg else 0.0
    return values


def aggregate_metrics(rows: Iterable[dict[str, float]]) -> dict[str, float]:
    materialized = list(rows)
    if not materialized:
        return {}
    return {
        key: mean(row[key] for row in materialized)
        for key in materialized[0]
    }


def grouped_metrics(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, float]]] = defaultdict(list)
    for record in records:
        groups[record[field]].append(record["metrics"])
    return {name: aggregate_metrics(rows) for name, rows in sorted(groups.items())}


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "count": float(len(values)),
        "mean_seconds": mean(values) if values else 0.0,
        "p50_seconds": percentile(values, 0.50),
        "p95_seconds": percentile(values, 0.95),
        "p99_seconds": percentile(values, 0.99),
    }
