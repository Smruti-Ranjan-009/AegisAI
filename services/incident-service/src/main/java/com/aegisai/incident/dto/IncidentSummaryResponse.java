package com.aegisai.incident.dto;

import com.aegisai.incident.domain.IncidentSeverity;
import com.aegisai.incident.domain.IncidentStatus;
import java.time.Instant;
import java.util.UUID;

public record IncidentSummaryResponse(
        UUID id,
        String title,
        IncidentSeverity severity,
        IncidentStatus status,
        String owner,
        Instant createdAt,
        Instant updatedAt,
        long version) {
}
