package com.aegisai.incident.dto;

import com.aegisai.incident.domain.IncidentSeverity;
import com.aegisai.incident.domain.IncidentStatus;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

public record IncidentResponse(
        UUID id,
        String title,
        String description,
        IncidentSeverity severity,
        IncidentStatus status,
        String owner,
        Set<String> affectedServices,
        String rootCause,
        String remediation,
        Instant createdAt,
        Instant updatedAt,
        Instant resolvedAt,
        Instant closedAt,
        long version) {
}
