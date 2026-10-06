package com.aegisai.incident.dto;

import com.aegisai.incident.domain.IncidentSeverity;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateIncidentRequest(
        @NotBlank @Size(max = 200) String title,
        @Size(max = 10_000) String description,
        @NotNull IncidentSeverity severity,
        @Size(max = 200) String owner,
        @Size(max = 100) List<@NotBlank @Size(max = 200) String> affectedServices) {
}
