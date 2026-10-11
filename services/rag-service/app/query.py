from __future__ import annotations

from .contracts import DiagnosisRequest

QUERY_VERSION = "incident_query_v1"


def build_incident_query(request: DiagnosisRequest) -> str:
    signals = (
        "; ".join(f"{signal.name}={signal.value}" for signal in request.signal_summary)
        or "none supplied"
    )
    services = ", ".join(sorted(dict.fromkeys(request.affected_services)))
    return "\n".join(
        (
            f"Query contract: {QUERY_VERSION}",
            f"Incident title: {request.title}",
            f"Incident description: {request.description}",
            f"Affected services: {services}",
            f"Observed signals: {signals}",
            (
                "Anomaly detector output: score "
                f"{request.anomaly.anomaly_score:.8g} exceeded threshold "
                f"{request.anomaly.threshold:.8g}."
            ),
            (
                "Classifier prediction (unverified machine hint, not ground truth): "
                f"{request.classification.predicted_incident_type}."
            ),
            (
                "Find broadly relevant operational evidence for suspected causes "
                "and safe diagnostic actions."
            ),
        )
    )
