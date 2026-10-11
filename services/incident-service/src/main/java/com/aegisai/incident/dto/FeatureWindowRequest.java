package com.aegisai.incident.dto;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;

public record FeatureWindowRequest(
        @NotBlank @Size(max = 200) String windowId,
        @NotBlank @Size(max = 200) String serviceName,
        Instant windowStartUtc,
        Instant windowEndUtc,
        @NotEmpty @Size(max = 100) List<Double> values) {

    @AssertTrue(message = "window timestamps and feature values must be valid")
    @JsonIgnore
    public boolean isValidWindow() {
        return windowStartUtc != null
                && windowEndUtc != null
                && windowEndUtc.isAfter(windowStartUtc)
                && values != null
                && values.stream().allMatch(value -> value == null || Double.isFinite(value));
    }
}

