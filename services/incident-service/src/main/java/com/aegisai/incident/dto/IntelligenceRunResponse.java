package com.aegisai.incident.dto;

import com.aegisai.incident.domain.IntelligenceRunStatus;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.UUID;

public record IntelligenceRunResponse(
        UUID runId,
        UUID incidentId,
        String schemaVersion,
        String inputId,
        String requestHash,
        IntelligenceRunStatus status,
        boolean requiresHumanReview,
        String correlationId,
        JsonNode ml,
        JsonNode intelligence,
        JsonNode lineage,
        JsonNode timings,
        String failureCode,
        String failureMessage,
        Instant createdAt,
        Instant updatedAt,
        Instant completedAt,
        long version) {
}

