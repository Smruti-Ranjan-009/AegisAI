package com.aegisai.incident.domain;

public enum IncidentStatus {
    OPEN,
    INVESTIGATING,
    MITIGATED,
    RESOLVED,
    CLOSED;

    public boolean canTransitionTo(IncidentStatus target) {
        return switch (this) {
            case OPEN -> target == INVESTIGATING || target == RESOLVED;
            case INVESTIGATING -> target == MITIGATED || target == RESOLVED;
            case MITIGATED -> target == INVESTIGATING || target == RESOLVED;
            case RESOLVED -> target == INVESTIGATING || target == CLOSED;
            case CLOSED -> false;
        };
    }
}
