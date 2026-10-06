package com.aegisai.incident.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aegisai.incident.PostgreSqlIntegrationTest;
import com.aegisai.incident.domain.IncidentEntity;
import com.aegisai.incident.domain.IncidentSeverity;
import com.aegisai.incident.domain.IncidentStatus;
import com.aegisai.incident.domain.TimelineEntryEntity;
import com.aegisai.incident.domain.TimelineEventType;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class PostgreSqlPersistenceIntegrationTest extends PostgreSqlIntegrationTest {

    @Autowired
    private IncidentRepository incidentRepository;

    @Autowired
    private TimelineEntryRepository timelineRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @BeforeEach
    void cleanDatabase() {
        timelineRepository.deleteAll();
        incidentRepository.deleteAll();
    }

    @Test
    void flywayAppliedAllPhaseThreeMigrations() {
        Integer migrationCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history WHERE success = true",
                Integer.class);
        assertThat(migrationCount).isEqualTo(6);
    }

    @Test
    void failedTimelineWriteRollsBackIncidentWrite() {
        UUID incidentId = UUID.randomUUID();
        TransactionTemplate transaction = new TransactionTemplate(transactionManager);

        assertThatThrownBy(() -> transaction.executeWithoutResult(ignored -> {
            incidentRepository.saveAndFlush(newIncident(incidentId));
            timelineRepository.saveAndFlush(TimelineEntryEntity.create(
                    UUID.randomUUID(),
                    incidentId,
                    TimelineEventType.INCIDENT_CREATED,
                    null,
                    null,
                    Instant.now()));
        })).isInstanceOf(DataIntegrityViolationException.class);

        assertThat(incidentRepository.existsById(incidentId)).isFalse();
    }

    @Test
    void staleEntityCannotOverwriteNewerVersion() {
        UUID incidentId = UUID.randomUUID();
        TransactionTemplate transaction = new TransactionTemplate(transactionManager);
        transaction.executeWithoutResult(ignored -> incidentRepository.save(newIncident(incidentId)));

        IncidentEntity stale = transaction.execute(ignored -> incidentRepository.findById(incidentId).orElseThrow());
        transaction.executeWithoutResult(ignored -> {
            IncidentEntity current = incidentRepository.findById(incidentId).orElseThrow();
            current.transitionTo(IncidentStatus.RESOLVED, Instant.now());
        });
        stale.transitionTo(IncidentStatus.INVESTIGATING, Instant.now());

        assertThatThrownBy(() -> transaction.executeWithoutResult(
                ignored -> incidentRepository.saveAndFlush(stale)))
                .isInstanceOf(OptimisticLockingFailureException.class);
    }

    private static IncidentEntity newIncident(UUID id) {
        return IncidentEntity.create(
                id,
                "Database incident",
                "Integration test",
                IncidentSeverity.HIGH,
                "platform-team",
                Set.of("checkout-service"),
                Instant.now());
    }
}
