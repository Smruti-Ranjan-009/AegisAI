package com.aegisai.incident.domain;

import com.aegisai.incident.exception.InvalidIncidentTransitionException;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

@Entity
@Table(name = "incidents")
public class IncidentEntity {

    @Id
    private UUID id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(columnDefinition = "text")
    private String description;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private IncidentSeverity severity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private IncidentStatus status;

    @Column(length = 200)
    private String owner;

    @Column(name = "root_cause", columnDefinition = "text")
    private String rootCause;

    @Column(columnDefinition = "text")
    private String remediation;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
            name = "incident_affected_services",
            joinColumns = @JoinColumn(name = "incident_id"))
    @Column(name = "service_name", nullable = false, length = 200)
    private Set<String> affectedServices = new LinkedHashSet<>();

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "resolved_at")
    private Instant resolvedAt;

    @Column(name = "closed_at")
    private Instant closedAt;

    @Version
    @Column(nullable = false)
    private Long version;

    protected IncidentEntity() {
    }

    public static IncidentEntity create(
            UUID id,
            String title,
            String description,
            IncidentSeverity severity,
            String owner,
            Set<String> affectedServices,
            Instant now) {
        IncidentEntity incident = new IncidentEntity();
        incident.id = id;
        incident.title = title;
        incident.description = description;
        incident.severity = severity;
        incident.status = IncidentStatus.OPEN;
        incident.owner = owner;
        incident.affectedServices.addAll(affectedServices);
        incident.createdAt = now;
        incident.updatedAt = now;
        return incident;
    }

    public void updateDetails(
            String title,
            String description,
            IncidentSeverity severity,
            String owner,
            Set<String> affectedServices,
            String rootCause,
            String remediation,
            Instant now) {
        this.title = title;
        this.description = description;
        this.severity = severity;
        this.owner = owner;
        this.affectedServices.clear();
        this.affectedServices.addAll(affectedServices);
        this.rootCause = rootCause;
        this.remediation = remediation;
        this.updatedAt = now;
    }

    public void transitionTo(IncidentStatus target, Instant now) {
        if (!status.canTransitionTo(target)) {
            throw new InvalidIncidentTransitionException(id, status, target);
        }
        if (target == IncidentStatus.RESOLVED) {
            resolvedAt = now;
        } else if (status == IncidentStatus.RESOLVED && target == IncidentStatus.INVESTIGATING) {
            resolvedAt = null;
        }
        if (target == IncidentStatus.CLOSED) {
            closedAt = now;
        }
        status = target;
        updatedAt = now;
    }

    public UUID getId() { return id; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public IncidentSeverity getSeverity() { return severity; }
    public IncidentStatus getStatus() { return status; }
    public String getOwner() { return owner; }
    public String getRootCause() { return rootCause; }
    public String getRemediation() { return remediation; }
    public Set<String> getAffectedServices() { return Set.copyOf(affectedServices); }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getResolvedAt() { return resolvedAt; }
    public Instant getClosedAt() { return closedAt; }
    public long getVersion() { return version == null ? 0L : version; }
}
