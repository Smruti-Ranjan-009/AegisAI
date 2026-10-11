package com.aegisai.incident.exception;

import java.util.UUID;

public class IntelligenceRunNotFoundException extends RuntimeException {
    public IntelligenceRunNotFoundException(UUID incidentId, UUID runId) {
        super("Intelligence run %s was not found for incident %s".formatted(runId, incidentId));
    }
}
