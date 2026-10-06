package com.aegisai.incident.service;

import com.aegisai.incident.domain.IncidentEntity;
import com.aegisai.incident.domain.TimelineEntryEntity;
import com.aegisai.incident.dto.IncidentResponse;
import com.aegisai.incident.dto.IncidentSummaryResponse;
import com.aegisai.incident.dto.TimelineEntryResponse;
import org.springframework.stereotype.Component;

@Component
public class IncidentMapper {

    public IncidentResponse toResponse(IncidentEntity incident) {
        return new IncidentResponse(
                incident.getId(),
                incident.getTitle(),
                incident.getDescription(),
                incident.getSeverity(),
                incident.getStatus(),
                incident.getOwner(),
                incident.getAffectedServices(),
                incident.getRootCause(),
                incident.getRemediation(),
                incident.getCreatedAt(),
                incident.getUpdatedAt(),
                incident.getResolvedAt(),
                incident.getClosedAt(),
                incident.getVersion());
    }

    public IncidentSummaryResponse toSummary(IncidentEntity incident) {
        return new IncidentSummaryResponse(
                incident.getId(),
                incident.getTitle(),
                incident.getSeverity(),
                incident.getStatus(),
                incident.getOwner(),
                incident.getCreatedAt(),
                incident.getUpdatedAt(),
                incident.getVersion());
    }

    public TimelineEntryResponse toTimelineResponse(TimelineEntryEntity entry) {
        return new TimelineEntryResponse(
                entry.getId(),
                entry.getIncidentId(),
                entry.getEventType(),
                entry.getMessage(),
                entry.getActor(),
                entry.getCreatedAt());
    }
}
