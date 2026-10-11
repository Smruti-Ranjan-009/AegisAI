package com.aegisai.incident.repository;

import com.aegisai.incident.domain.IntelligenceRunEntity;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IntelligenceRunRepository extends JpaRepository<IntelligenceRunEntity, UUID> {
    Optional<IntelligenceRunEntity> findByIncidentIdAndRequestHash(UUID incidentId, String requestHash);

    Optional<IntelligenceRunEntity> findByIdAndIncidentId(UUID id, UUID incidentId);

    Page<IntelligenceRunEntity> findByIncidentId(UUID incidentId, Pageable pageable);

    @Modifying
    @Query(value = """
            INSERT INTO incident_intelligence_runs (
                id, incident_id, request_hash, status, schema_version, input_id,
                correlation_id, requires_human_review, created_at, updated_at, version
            ) VALUES (
                :id, :incidentId, :requestHash, 'PENDING', :schemaVersion, :inputId,
                :correlationId, TRUE, :now, :now, 0
            ) ON CONFLICT (incident_id, request_hash) DO NOTHING
            """, nativeQuery = true)
    int claim(
            @Param("id") UUID id,
            @Param("incidentId") UUID incidentId,
            @Param("requestHash") String requestHash,
            @Param("schemaVersion") String schemaVersion,
            @Param("inputId") String inputId,
            @Param("correlationId") String correlationId,
            @Param("now") Instant now);
}

