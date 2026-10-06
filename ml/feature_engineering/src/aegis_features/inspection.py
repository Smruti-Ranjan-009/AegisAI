from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .loaders import SIGNALS, iter_signal_records, load_manifest
from .otlp import normalize_record


def inspect_run(raw_root: Path, run_id: str) -> dict[str, Any]:
    run = load_manifest(raw_root, run_id)
    records = Counter()
    observations = Counter()
    services: set[str] = set()
    metric_inventory: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    severities = Counter()
    span_kinds = Counter()
    for signal in SIGNALS:
        for record in iter_signal_records(run, signal):
            records[signal] += 1
            batch = normalize_record(record)
            observations["metrics"] += len(batch.metrics)
            observations["logs"] += len(batch.logs)
            observations["traces"] += len(batch.spans)
            services.update(observation.service_name for observation in batch.observations)
            for metric in batch.metrics:
                metric_inventory[(metric.metric_name, metric.unit, metric.metric_type)].add(
                    metric.service_name
                )
            severities.update(log.severity_group for log in batch.logs)
            span_kinds.update(span.span_kind for span in batch.spans)
    return {
        "run_id": run.run_id,
        "scenario": run.scenario,
        "label": run.label,
        "validation": "PASS",
        "input_records_by_signal": dict(sorted(records.items())),
        "observations_by_signal": dict(sorted(observations.items())),
        "services": sorted(services),
        "metric_inventory": [
            {
                "metric_name": name,
                "unit": unit,
                "metric_type": metric_type,
                "services": sorted(metric_services),
            }
            for (name, unit, metric_type), metric_services in sorted(metric_inventory.items())
        ],
        "log_severity_distribution": dict(sorted(severities.items())),
        "span_kind_distribution": dict(sorted(span_kinds.items())),
    }


def combine_inventories(inventories: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    severities = Counter()
    span_kinds = Counter()
    for inventory in inventories:
        for metric in inventory["metric_inventory"]:
            key = (metric["metric_name"], metric["unit"], metric["metric_type"])
            metrics[key].update(metric["services"])
        severities.update(inventory["log_severity_distribution"])
        span_kinds.update(inventory["span_kind_distribution"])
    return {
        "runs": [inventory["run_id"] for inventory in inventories],
        "metrics": [
            {
                "metric_name": name,
                "unit": unit,
                "metric_type": metric_type,
                "services": sorted(services),
            }
            for (name, unit, metric_type), services in sorted(metrics.items())
        ],
        "log_severity_distribution": dict(sorted(severities.items())),
        "span_kind_distribution": dict(sorted(span_kinds.items())),
    }
