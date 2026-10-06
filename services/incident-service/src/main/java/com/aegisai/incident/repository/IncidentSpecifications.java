package com.aegisai.incident.repository;

import com.aegisai.incident.domain.IncidentEntity;
import com.aegisai.incident.domain.IncidentSeverity;
import com.aegisai.incident.domain.IncidentStatus;
import jakarta.persistence.criteria.JoinType;
import org.springframework.data.jpa.domain.Specification;

public final class IncidentSpecifications {

    private IncidentSpecifications() {
    }

    public static Specification<IncidentEntity> withFilters(
            IncidentStatus status,
            IncidentSeverity severity,
            String service,
            String owner) {
        return Specification.allOf(
                equalsStatus(status),
                equalsSeverity(severity),
                hasAffectedService(service),
                equalsOwner(owner));
    }

    private static Specification<IncidentEntity> equalsStatus(IncidentStatus status) {
        return status == null ? null : (root, query, builder) -> builder.equal(root.get("status"), status);
    }

    private static Specification<IncidentEntity> equalsSeverity(IncidentSeverity severity) {
        return severity == null ? null : (root, query, builder) -> builder.equal(root.get("severity"), severity);
    }

    private static Specification<IncidentEntity> hasAffectedService(String service) {
        if (service == null || service.isBlank()) {
            return null;
        }
        return (root, query, builder) -> {
            query.distinct(true);
            return builder.equal(
                    root.joinSet("affectedServices", JoinType.INNER),
                    service.strip().toLowerCase(java.util.Locale.ROOT));
        };
    }

    private static Specification<IncidentEntity> equalsOwner(String owner) {
        if (owner == null || owner.isBlank()) {
            return null;
        }
        return (root, query, builder) -> builder.equal(
                builder.lower(root.get("owner")),
                owner.strip().toLowerCase(java.util.Locale.ROOT));
    }
}
