package com.aegisai.incident.service;

import com.aegisai.incident.domain.IncidentEntity;
import com.aegisai.incident.domain.IncidentSeverity;
import com.aegisai.incident.domain.IncidentStatus;
import com.aegisai.incident.domain.TimelineEntryEntity;
import com.aegisai.incident.domain.TimelineEventType;
import com.aegisai.incident.dto.AddTimelineNoteRequest;
import com.aegisai.incident.dto.CreateIncidentRequest;
import com.aegisai.incident.dto.IncidentResponse;
import com.aegisai.incident.dto.IncidentSummaryResponse;
import com.aegisai.incident.dto.PageResponse;
import com.aegisai.incident.dto.TimelineEntryResponse;
import com.aegisai.incident.dto.TransitionIncidentRequest;
import com.aegisai.incident.dto.UpdateIncidentRequest;
import com.aegisai.incident.exception.IncidentNotFoundException;
import com.aegisai.incident.repository.IncidentRepository;
import com.aegisai.incident.repository.IncidentSpecifications;
import com.aegisai.incident.repository.TimelineEntryRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IncidentService {

    private static final Logger LOGGER = LoggerFactory.getLogger(IncidentService.class);

    private final IncidentRepository incidentRepository;
    private final TimelineEntryRepository timelineRepository;
    private final IncidentMapper mapper;
    private final Clock clock;

    public IncidentService(
            IncidentRepository incidentRepository,
            TimelineEntryRepository timelineRepository,
            IncidentMapper mapper,
            Clock clock) {
        this.incidentRepository = incidentRepository;
        this.timelineRepository = timelineRepository;
        this.mapper = mapper;
        this.clock = clock;
    }

    @Transactional
    public IncidentResponse create(CreateIncidentRequest request) {
        Instant now = clock.instant();
        IncidentEntity incident = IncidentEntity.create(
                UUID.randomUUID(),
                request.title().strip(),
                nullableText(request.description()),
                request.severity(),
                nullableText(request.owner()),
                normalizeServices(request.affectedServices()),
                now);
        incidentRepository.save(incident);
        timelineRepository.saveAndFlush(TimelineEntryEntity.create(
                UUID.randomUUID(),
                incident.getId(),
                TimelineEventType.INCIDENT_CREATED,
                "Incident created",
                incident.getOwner(),
                now));
        LOGGER.info("Incident created: incidentId={}, severity={}", incident.getId(), incident.getSeverity());
        return mapper.toResponse(incident);
    }

    @Transactional(readOnly = true)
    public IncidentResponse get(UUID incidentId) {
        return mapper.toResponse(findIncident(incidentId));
    }

    @Transactional(readOnly = true)
    public PageResponse<IncidentSummaryResponse> list(
            IncidentStatus status,
            IncidentSeverity severity,
            String service,
            String owner,
            int page,
            int size) {
        PageRequest pageable = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
        Page<IncidentSummaryResponse> result = incidentRepository
                .findAll(IncidentSpecifications.withFilters(status, severity, service, owner), pageable)
                .map(mapper::toSummary);
        return PageResponse.from(result);
    }

    @Transactional
    public IncidentResponse update(UUID incidentId, UpdateIncidentRequest request) {
        IncidentEntity incident = findIncident(incidentId);
        Instant now = clock.instant();
        List<TimelineEntryEntity> entries = new ArrayList<>();

        boolean detailsChanged = request.title() != null
                || request.description() != null
                || request.severity() != null
                || request.owner() != null
                || request.affectedServices() != null;
        boolean rootCauseChanged = request.rootCause() != null
                && !Objects.equals(incident.getRootCause(), nullableText(request.rootCause()));
        boolean remediationChanged = request.remediation() != null
                && !Objects.equals(incident.getRemediation(), nullableText(request.remediation()));

        String title = request.title() == null ? incident.getTitle() : request.title().strip();
        String description = request.description() == null
                ? incident.getDescription() : nullableText(request.description());
        IncidentSeverity severity = request.severity() == null
                ? incident.getSeverity() : request.severity();
        String owner = request.owner() == null ? incident.getOwner() : nullableText(request.owner());
        Set<String> services = request.affectedServices() == null
                ? incident.getAffectedServices() : normalizeServices(request.affectedServices());
        String rootCause = request.rootCause() == null
                ? incident.getRootCause() : nullableText(request.rootCause());
        String remediation = request.remediation() == null
                ? incident.getRemediation() : nullableText(request.remediation());

        incident.updateDetails(title, description, severity, owner, services, rootCause, remediation, now);
        if (detailsChanged) {
            entries.add(timeline(incidentId, TimelineEventType.DETAILS_UPDATED,
                    "Incident details updated", null, now));
        }
        if (rootCauseChanged) {
            entries.add(timeline(incidentId, TimelineEventType.ROOT_CAUSE_UPDATED,
                    "Root cause updated", null, now));
        }
        if (remediationChanged) {
            entries.add(timeline(incidentId, TimelineEventType.REMEDIATION_UPDATED,
                    "Remediation updated", null, now));
        }
        if (!entries.isEmpty()) {
            timelineRepository.saveAll(entries);
        }
        incidentRepository.flush();
        LOGGER.info("Incident updated: incidentId={}, timelineEntries={}", incidentId, entries.size());
        return mapper.toResponse(incident);
    }

    @Transactional
    public IncidentResponse transition(UUID incidentId, TransitionIncidentRequest request) {
        IncidentEntity incident = findIncident(incidentId);
        IncidentStatus previous = incident.getStatus();
        Instant now = clock.instant();
        incident.transitionTo(request.targetStatus(), now);
        String message = "%s -> %s".formatted(previous, request.targetStatus());
        if (request.note() != null && !request.note().isBlank()) {
            message += ": " + request.note().strip();
        }
        timelineRepository.save(timeline(
                incidentId,
                TimelineEventType.STATUS_CHANGED,
                message,
                nullableText(request.actor()),
                now));
        incidentRepository.flush();
        LOGGER.info(
                "Incident transitioned: incidentId={}, from={}, to={}",
                incidentId,
                previous,
                request.targetStatus());
        return mapper.toResponse(incident);
    }

    @Transactional
    public TimelineEntryResponse addTimelineNote(UUID incidentId, AddTimelineNoteRequest request) {
        if (!incidentRepository.existsById(incidentId)) {
            throw new IncidentNotFoundException(incidentId);
        }
        TimelineEntryEntity entry = timelineRepository.save(TimelineEntryEntity.create(
                UUID.randomUUID(),
                incidentId,
                TimelineEventType.NOTE_ADDED,
                request.message().strip(),
                nullableText(request.actor()),
                clock.instant()));
        LOGGER.info("Timeline note added: incidentId={}, entryId={}", incidentId, entry.getId());
        return mapper.toTimelineResponse(entry);
    }

    @Transactional(readOnly = true)
    public PageResponse<TimelineEntryResponse> getTimeline(UUID incidentId, int page, int size) {
        if (!incidentRepository.existsById(incidentId)) {
            throw new IncidentNotFoundException(incidentId);
        }
        PageRequest pageable = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Order.asc("createdAt"), Sort.Order.asc("id")));
        return PageResponse.from(timelineRepository.findByIncidentId(incidentId, pageable)
                .map(mapper::toTimelineResponse));
    }

    private IncidentEntity findIncident(UUID incidentId) {
        return incidentRepository.findById(incidentId)
                .orElseThrow(() -> new IncidentNotFoundException(incidentId));
    }

    private static TimelineEntryEntity timeline(
            UUID incidentId,
            TimelineEventType eventType,
            String message,
            String actor,
            Instant now) {
        return TimelineEntryEntity.create(UUID.randomUUID(), incidentId, eventType, message, actor, now);
    }

    private static Set<String> normalizeServices(List<String> services) {
        if (services == null) {
            return Set.of();
        }
        Set<String> normalized = new LinkedHashSet<>();
        services.forEach(service -> normalized.add(service.strip().toLowerCase(Locale.ROOT)));
        return normalized;
    }

    private static String nullableText(String value) {
        return value == null || value.isBlank() ? null : value.strip();
    }
}
