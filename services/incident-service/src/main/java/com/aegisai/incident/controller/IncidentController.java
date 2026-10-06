package com.aegisai.incident.controller;

import com.aegisai.incident.domain.IncidentSeverity;
import com.aegisai.incident.domain.IncidentStatus;
import com.aegisai.incident.dto.AddTimelineNoteRequest;
import com.aegisai.incident.dto.CreateIncidentRequest;
import com.aegisai.incident.dto.IncidentResponse;
import com.aegisai.incident.dto.IncidentSummaryResponse;
import com.aegisai.incident.dto.PageResponse;
import com.aegisai.incident.dto.TimelineEntryResponse;
import com.aegisai.incident.dto.TransitionIncidentRequest;
import com.aegisai.incident.dto.UpdateIncidentRequest;
import com.aegisai.incident.service.IncidentService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/incidents")
public class IncidentController {

    private final IncidentService incidentService;

    public IncidentController(IncidentService incidentService) {
        this.incidentService = incidentService;
    }

    @PostMapping
    public ResponseEntity<IncidentResponse> create(@Valid @RequestBody CreateIncidentRequest request) {
        IncidentResponse response = incidentService.create(request);
        return ResponseEntity.created(URI.create("/api/v1/incidents/" + response.id())).body(response);
    }

    @GetMapping("/{incidentId}")
    public IncidentResponse get(@PathVariable UUID incidentId) {
        return incidentService.get(incidentId);
    }

    @GetMapping
    public PageResponse<IncidentSummaryResponse> list(
            @RequestParam(required = false) IncidentStatus status,
            @RequestParam(required = false) IncidentSeverity severity,
            @RequestParam(required = false) String service,
            @RequestParam(required = false) String owner,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return incidentService.list(status, severity, service, owner, page, size);
    }

    @PatchMapping("/{incidentId}")
    public IncidentResponse update(
            @PathVariable UUID incidentId,
            @Valid @RequestBody UpdateIncidentRequest request) {
        return incidentService.update(incidentId, request);
    }

    @PostMapping("/{incidentId}/transition")
    public IncidentResponse transition(
            @PathVariable UUID incidentId,
            @Valid @RequestBody TransitionIncidentRequest request) {
        return incidentService.transition(incidentId, request);
    }

    @PostMapping("/{incidentId}/timeline")
    public ResponseEntity<TimelineEntryResponse> addTimelineNote(
            @PathVariable UUID incidentId,
            @Valid @RequestBody AddTimelineNoteRequest request) {
        TimelineEntryResponse response = incidentService.addTimelineNote(incidentId, request);
        return ResponseEntity
                .created(URI.create("/api/v1/incidents/%s/timeline/%s".formatted(incidentId, response.id())))
                .body(response);
    }

    @GetMapping("/{incidentId}/timeline")
    public PageResponse<TimelineEntryResponse> getTimeline(
            @PathVariable UUID incidentId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "100") @Min(1) @Max(100) int size) {
        return incidentService.getTimeline(incidentId, page, size);
    }
}
