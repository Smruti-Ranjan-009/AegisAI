package com.aegisai.incident.exception;

import java.util.UUID;

public class IncidentNotFoundException extends RuntimeException {

    public IncidentNotFoundException(UUID incidentId) {
        super("Incident %s was not found".formatted(incidentId));
    }
}
