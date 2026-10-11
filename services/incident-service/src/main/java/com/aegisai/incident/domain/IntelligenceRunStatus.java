package com.aegisai.incident.domain;

public enum IntelligenceRunStatus {
    PENDING,
    RUNNING,
    NO_ANOMALY_SIGNAL,
    GROUNDED_ADVISORY,
    INSUFFICIENT_EVIDENCE,
    FAILED_ML,
    FAILED_RAG,
    FAILED_VALIDATION
}

