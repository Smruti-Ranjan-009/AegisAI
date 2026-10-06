package com.aegisai.incident.exception;

import com.aegisai.incident.domain.IncidentStatus;
import java.util.UUID;

public class InvalidIncidentTransitionException extends RuntimeException {

    public InvalidIncidentTransitionException(UUID incidentId, IncidentStatus from, IncidentStatus to) {
        super("Incident %s cannot transition from %s to %s".formatted(incidentId, from, to));
    }
}
