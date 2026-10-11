package com.aegisai.incident.domain;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "incident_intelligence_runs")
public class IntelligenceRunEntity {
    @Id
    private UUID id;

    @Column(name = "incident_id", nullable = false)
    private UUID incidentId;

    @Column(name = "request_hash", nullable = false, length = 64)
    private String requestHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private IntelligenceRunStatus status;

    @Column(name = "schema_version", nullable = false, length = 40)
    private String schemaVersion;

    @Column(name = "input_id", nullable = false, length = 200)
    private String inputId;

    @Column(name = "correlation_id", nullable = false, length = 200)
    private String correlationId;

    @Column(name = "requires_human_review", nullable = false)
    private boolean requiresHumanReview;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "ml_result", columnDefinition = "jsonb")
    private JsonNode mlResult;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "intelligence_result", columnDefinition = "jsonb")
    private JsonNode intelligenceResult;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private JsonNode lineage;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private JsonNode timings;

    @Column(name = "failure_code", length = 80)
    private String failureCode;

    @Column(name = "failure_message", columnDefinition = "text")
    private String failureMessage;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "completed_at")
    private Instant completedAt;

    @Version
    @Column(nullable = false)
    private Long version;

    protected IntelligenceRunEntity() {
    }

    public void markRunning(Instant now) {
        status = IntelligenceRunStatus.RUNNING;
        updatedAt = now;
    }

    public void complete(
            IntelligenceRunStatus nextStatus,
            JsonNode ml,
            JsonNode intelligence,
            JsonNode runLineage,
            JsonNode runTimings,
            Instant now) {
        status = nextStatus;
        mlResult = ml;
        intelligenceResult = intelligence;
        lineage = runLineage;
        timings = runTimings;
        failureCode = null;
        failureMessage = null;
        updatedAt = now;
        completedAt = now;
    }

    public void fail(
            IntelligenceRunStatus nextStatus,
            String code,
            String message,
            JsonNode ml,
            JsonNode runLineage,
            JsonNode runTimings,
            Instant now) {
        status = nextStatus;
        failureCode = code;
        failureMessage = message;
        mlResult = ml;
        lineage = runLineage;
        timings = runTimings;
        updatedAt = now;
        completedAt = now;
    }

    public UUID getId() { return id; }
    public UUID getIncidentId() { return incidentId; }
    public String getRequestHash() { return requestHash; }
    public IntelligenceRunStatus getStatus() { return status; }
    public String getSchemaVersion() { return schemaVersion; }
    public String getInputId() { return inputId; }
    public String getCorrelationId() { return correlationId; }
    public boolean isRequiresHumanReview() { return requiresHumanReview; }
    public JsonNode getMlResult() { return mlResult; }
    public JsonNode getIntelligenceResult() { return intelligenceResult; }
    public JsonNode getLineage() { return lineage; }
    public JsonNode getTimings() { return timings; }
    public String getFailureCode() { return failureCode; }
    public String getFailureMessage() { return failureMessage; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getCompletedAt() { return completedAt; }
    public long getVersion() { return version == null ? 0L : version; }
}

