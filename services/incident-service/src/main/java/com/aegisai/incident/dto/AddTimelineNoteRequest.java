package com.aegisai.incident.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AddTimelineNoteRequest(
        @NotBlank @Size(max = 5_000) String message,
        @Size(max = 200) String actor) {
}
