package com.aegisai.incident.dto;

import com.aegisai.incident.domain.IncidentStatus;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record TransitionIncidentRequest(
        @NotNull IncidentStatus targetStatus,
        @Size(max = 5_000) String note,
        @Size(max = 200) String actor) {
}
