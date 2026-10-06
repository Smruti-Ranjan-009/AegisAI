package com.aegisai.incident.dto;

import com.aegisai.incident.domain.TimelineEventType;
import java.time.Instant;
import java.util.UUID;

public record TimelineEntryResponse(
        UUID id,
        UUID incidentId,
        TimelineEventType eventType,
        String message,
        String actor,
        Instant createdAt) {
}
