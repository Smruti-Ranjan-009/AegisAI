"""Run the five Phase 12 controlled integration smokes against local services."""

from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from aegis_anomaly.artifacts import load_bundle
from aegis_anomaly.data import load_feature_dataset
from aegis_anomaly.labels import load_ground_truth

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = (
    "cpu_saturation",
    "memory_leak",
    "service_failure",
    "dependency_failure",
    "high_latency",
)


def post(url: str, body: dict[str, Any], correlation_id: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        data=json.dumps(body, allow_nan=False).encode(),
        headers={"Content-Type": "application/json", "X-Correlation-ID": correlation_id},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=400) as response:
        return json.load(response), (time.perf_counter() - started) * 1000


def main() -> None:
    base_url = os.getenv("AEGIS_INCIDENT_SERVICE_URL", "http://127.0.0.1:8080")
    validation_identity = os.getenv(
        "AEGIS_PHASE12_VALIDATION_IDENTITY", "contract-fix-20261011"
    )
    dataset = load_feature_dataset("phase4-v1-45ebffa2ddf3")
    bundle = load_bundle(
        ROOT / "artifacts" / "anomaly_detection" / "anomaly-v1-4c84405c580f" / "model.joblib"
    )
    matrix, _ = bundle.matrix_and_scores(dataset, load_ground_truth())
    grouped: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for index, metadata in enumerate(matrix.metadata):
        grouped[(str(metadata["scenario"]), str(metadata["run_id"]))].append(index)

    results: list[dict[str, Any]] = []
    for family in FAMILIES:
        run_id = sorted(run for scenario, run in grouped if scenario == family)[0]
        indices = grouped[(family, run_id)]
        services = sorted({str(matrix.metadata[index]["service_name"]) for index in indices})
        input_id = f"{run_id}-{validation_identity}"
        correlation_id = f"phase12-real-{family}-{validation_identity}"
        incident, _ = post(
            f"{base_url}/api/v1/incidents",
            {
                "title": f"Phase 12 controlled {family} smoke",
                "description": (
                    "Controlled local integration input from the frozen telemetry campaign; "
                    "this is not a new quality benchmark."
                ),
                "severity": "HIGH",
                "owner": "phase12-validation",
                "affected_services": services,
            },
            correlation_id,
        )
        windows = []
        for index in indices:
            metadata = matrix.metadata[index]
            windows.append(
                {
                    "window_id": str(metadata["window_id"]),
                    "service_name": str(metadata["service_name"]),
                    "window_start_utc": metadata["window_start_utc"].isoformat(),
                    "window_end_utc": metadata["window_end_utc"].isoformat(),
                    "values": [
                        None if not math.isfinite(float(value)) else float(value)
                        for value in matrix.values[index]
                    ],
                }
            )
        intelligence_request = {
            "schema_version": "intelligence_v1",
            "input_id": input_id,
            "feature_schema_version": 1,
            "feature_names": list(matrix.feature_names),
            "windows": windows,
            "signal_summary": [
                {"name": "controlled_fault_family", "value": family},
                {"name": "source_run_id", "value": run_id},
            ],
        }
        if family == FAMILIES[0]:
            debug = dict(intelligence_request)
            debug["schema_version"] = "ml_inference_v1"
            debug.pop("signal_summary")
            (ROOT / ".runtime" / "phase12-real-ml-request.json").write_text(
                json.dumps(debug, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
        run, elapsed_ms = post(
            f"{base_url}/api/v1/incidents/{incident['id']}/intelligence-runs",
            intelligence_request,
            correlation_id,
        )
        classification = (run.get("ml") or {}).get("classification") or {}
        intelligence = run.get("intelligence") or {}
        results.append(
            {
                "fault_family": family,
                "source_run_id": run_id,
                "input_id": input_id,
                "incident_id": incident["id"],
                "intelligence_run_id": run["run_id"],
                "anomaly_result": (run.get("ml") or {}).get("anomaly", {}).get("is_anomaly"),
                "anomaly_score": (run.get("ml") or {}).get("anomaly", {}).get("score"),
                "classifier_prediction": classification.get("predicted_incident_type"),
                "run_status": run["status"],
                "rag_status": intelligence.get("status"),
                "citation_count": len(intelligence.get("citations", [])),
                "component_timings_ms": run.get("timings"),
                "observed_http_ms": elapsed_ms,
            }
        )
        print(json.dumps(results[-1], sort_keys=True))

    output = ROOT / ".runtime" / "phase12-real-validation.json"
    output.write_text(json.dumps({"scenarios": results}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
