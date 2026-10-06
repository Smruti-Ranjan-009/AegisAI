package com.aegisai.incident.repository;

import com.aegisai.incident.domain.TimelineEntryEntity;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TimelineEntryRepository extends JpaRepository<TimelineEntryEntity, UUID> {

    Page<TimelineEntryEntity> findByIncidentId(UUID incidentId, Pageable pageable);
}
