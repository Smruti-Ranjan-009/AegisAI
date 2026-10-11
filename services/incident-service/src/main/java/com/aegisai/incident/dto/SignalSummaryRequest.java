package com.aegisai.incident.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignalSummaryRequest(
        @NotBlank @Size(max = 100) String name,
        @NotBlank @Size(max = 300) String value) {
}

