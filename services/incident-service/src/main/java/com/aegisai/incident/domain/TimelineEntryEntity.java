package com.aegisai.incident.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "incident_timeline_entries")
public class TimelineEntryEntity {

    @Id
    private UUID id;

    @Column(name = "incident_id", nullable = false)
    private UUID incidentId;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false, length = 40)
    private TimelineEventType eventType;

    @Column(nullable = false, columnDefinition = "text")
    private String message;

    @Column(length = 200)
    private String actor;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected TimelineEntryEntity() {
    }

    public static TimelineEntryEntity create(
            UUID id,
            UUID incidentId,
            TimelineEventType eventType,
            String message,
            String actor,
            Instant createdAt) {
        TimelineEntryEntity entry = new TimelineEntryEntity();
        entry.id = id;
        entry.incidentId = incidentId;
        entry.eventType = eventType;
        entry.message = message;
        entry.actor = actor;
        entry.createdAt = createdAt;
        return entry;
    }

    public UUID getId() { return id; }
    public UUID getIncidentId() { return incidentId; }
    public TimelineEventType getEventType() { return eventType; }
    public String getMessage() { return message; }
    public String getActor() { return actor; }
    public Instant getCreatedAt() { return createdAt; }
}
