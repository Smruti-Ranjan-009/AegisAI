package com.aegisai.incident.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

public record IntelligenceRunRequest(
        @NotBlank @Pattern(regexp = "intelligence_v1") String schemaVersion,
        @NotBlank @Size(max = 200) String inputId,
        @NotNull Integer featureSchemaVersion,
        @NotEmpty @Size(max = 100) List<@NotBlank String> featureNames,
        @NotEmpty @Size(max = 1000) List<@Valid FeatureWindowRequest> windows,
        @Size(max = 30) List<@Valid SignalSummaryRequest> signalSummary) {
}

