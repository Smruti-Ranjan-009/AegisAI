package com.aegisai.incident.controller;

import com.aegisai.incident.dto.IntelligenceRunRequest;
import com.aegisai.incident.dto.IntelligenceRunResponse;
import com.aegisai.incident.dto.PageResponse;
import com.aegisai.incident.service.IntelligenceService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.net.URI;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/incidents/{incidentId}/intelligence-runs")
public class IntelligenceController {
    private final IntelligenceService intelligenceService;

    public IntelligenceController(IntelligenceService intelligenceService) {
        this.intelligenceService = intelligenceService;
    }

    @PostMapping
    public ResponseEntity<IntelligenceRunResponse> run(
            @PathVariable UUID incidentId,
            @Valid @RequestBody IntelligenceRunRequest request,
            @RequestHeader(name = "X-Correlation-ID", required = false) String correlationId) {
        IntelligenceService.RunResult result = intelligenceService.run(incidentId, request, correlationId);
        IntelligenceRunResponse body = result.response();
        ResponseEntity.BodyBuilder builder = ResponseEntity
                .status(result.created() ? HttpStatus.CREATED : HttpStatus.OK)
                .header("X-Correlation-ID", body.correlationId());
        if (result.created()) {
            builder.location(URI.create(
                    "/api/v1/incidents/%s/intelligence-runs/%s".formatted(incidentId, body.runId())));
        }
        return builder.body(body);
    }

    @GetMapping
    public PageResponse<IntelligenceRunResponse> list(
            @PathVariable UUID incidentId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return intelligenceService.list(incidentId, page, size);
    }

    @GetMapping("/{runId}")
    public ResponseEntity<IntelligenceRunResponse> get(
            @PathVariable UUID incidentId,
            @PathVariable UUID runId) {
        IntelligenceRunResponse response = intelligenceService.get(incidentId, runId);
        return ResponseEntity.ok()
                .header("X-Correlation-ID", response.correlationId())
                .body(response);
    }
}

