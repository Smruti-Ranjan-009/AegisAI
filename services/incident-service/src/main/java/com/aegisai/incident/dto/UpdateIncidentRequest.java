package com.aegisai.incident.dto;

import com.aegisai.incident.domain.IncidentSeverity;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

public record UpdateIncidentRequest(
        @Pattern(regexp = ".*\\S.*", message = "must contain non-whitespace text")
        @Size(max = 200) String title,
        @Size(max = 10_000) String description,
        IncidentSeverity severity,
        @Size(max = 200) String owner,
        @Size(max = 100) List<@NotBlank @Size(max = 200) String> affectedServices,
        @Size(max = 10_000) String rootCause,
        @Size(max = 10_000) String remediation) {
}
