package com.aegisai.incident.repository;

import com.aegisai.incident.domain.IncidentEntity;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface IncidentRepository
        extends JpaRepository<IncidentEntity, UUID>, JpaSpecificationExecutor<IncidentEntity> {
}
