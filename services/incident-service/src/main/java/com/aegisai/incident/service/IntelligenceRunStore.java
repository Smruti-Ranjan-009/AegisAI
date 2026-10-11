package com.aegisai.incident.service;

import com.aegisai.incident.domain.IntelligenceRunEntity;
import com.aegisai.incident.domain.IntelligenceRunStatus;
import com.aegisai.incident.domain.TimelineEntryEntity;
import com.aegisai.incident.domain.TimelineEventType;
import com.aegisai.incident.exception.IntelligenceRunNotFoundException;
import com.aegisai.incident.repository.IntelligenceRunRepository;
import com.aegisai.incident.repository.TimelineEntryRepository;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Component
public class IntelligenceRunStore {
    private final IntelligenceRunRepository repository;
    private final TimelineEntryRepository timelineRepository;
    private final Clock clock;

    public IntelligenceRunStore(
            IntelligenceRunRepository repository,
            TimelineEntryRepository timelineRepository,
            Clock clock) {
        this.repository = repository;
        this.timelineRepository = timelineRepository;
        this.clock = clock;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public ClaimResult claim(
            UUID incidentId,
            String requestHash,
            String schemaVersion,
            String inputId,
            String correlationId) {
        UUID runId = UUID.randomUUID();
        Instant now = clock.instant();
        boolean claimed = repository.claim(
                runId, incidentId, requestHash, schemaVersion, inputId, correlationId, now) == 1;
        IntelligenceRunEntity entity = claimed
                ? repository.findById(runId).orElseThrow()
                : repository.findByIncidentIdAndRequestHash(incidentId, requestHash).orElseThrow();
        return new ClaimResult(claimed, entity);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public IntelligenceRunEntity markRunning(UUID incidentId, UUID runId) {
        IntelligenceRunEntity entity = find(incidentId, runId);
        Instant now = clock.instant();
        entity.markRunning(now);
        timelineRepository.save(TimelineEntryEntity.create(
                UUID.randomUUID(), incidentId, TimelineEventType.INTELLIGENCE_STARTED,
                "Incident intelligence analysis started", "incident-service", now));
        return repository.saveAndFlush(entity);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public IntelligenceRunEntity complete(
            UUID incidentId,
            UUID runId,
            IntelligenceRunStatus status,
            JsonNode ml,
            JsonNode intelligence,
            JsonNode lineage,
            JsonNode timings) {
        IntelligenceRunEntity entity = find(incidentId, runId);
        Instant now = clock.instant();
        entity.complete(status, ml, intelligence, lineage, timings, now);
        timelineRepository.save(TimelineEntryEntity.create(
                UUID.randomUUID(), incidentId, eventFor(status),
                messageFor(status), "incident-service", now));
        return repository.saveAndFlush(entity);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public IntelligenceRunEntity fail(
            UUID incidentId,
            UUID runId,
            IntelligenceRunStatus status,
            String code,
            String message,
            JsonNode ml,
            JsonNode lineage,
            JsonNode timings) {
        IntelligenceRunEntity entity = find(incidentId, runId);
        Instant now = clock.instant();
        entity.fail(status, code, message, ml, lineage, timings, now);
        timelineRepository.save(TimelineEntryEntity.create(
                UUID.randomUUID(), incidentId, TimelineEventType.INTELLIGENCE_FAILED,
                "Incident intelligence analysis failed: " + code, "incident-service", now));
        return repository.saveAndFlush(entity);
    }

    private IntelligenceRunEntity find(UUID incidentId, UUID runId) {
        return repository.findByIdAndIncidentId(runId, incidentId)
                .orElseThrow(() -> new IntelligenceRunNotFoundException(incidentId, runId));
    }

    private static TimelineEventType eventFor(IntelligenceRunStatus status) {
        return switch (status) {
            case NO_ANOMALY_SIGNAL -> TimelineEventType.ANOMALY_NOT_DETECTED;
            case GROUNDED_ADVISORY -> TimelineEventType.INTELLIGENCE_GROUNDED;
            case INSUFFICIENT_EVIDENCE -> TimelineEventType.INTELLIGENCE_ABSTAINED;
            default -> throw new IllegalArgumentException("status is not a successful terminal state");
        };
    }

    private static String messageFor(IntelligenceRunStatus status) {
        return switch (status) {
            case NO_ANOMALY_SIGNAL -> "Frozen anomaly model reported no anomaly signal";
            case GROUNDED_ADVISORY -> "Advisory incident intelligence generated; human review required";
            case INSUFFICIENT_EVIDENCE -> "Incident intelligence abstained for insufficient evidence";
            default -> throw new IllegalArgumentException("status is not a successful terminal state");
        };
    }

    public record ClaimResult(boolean claimed, IntelligenceRunEntity entity) {
    }
}

