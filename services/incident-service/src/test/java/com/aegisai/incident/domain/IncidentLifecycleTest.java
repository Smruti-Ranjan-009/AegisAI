package com.aegisai.incident.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aegisai.incident.exception.InvalidIncidentTransitionException;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class IncidentLifecycleTest {

    private static final Instant CREATED = Instant.parse("2026-01-01T00:00:00Z");
    private static final Instant CHANGED = Instant.parse("2026-01-02T00:00:00Z");

    @ParameterizedTest
    @MethodSource("transitionMatrix")
    void enforcesCompleteTransitionMatrix(IncidentStatus from, IncidentStatus to, boolean allowed) {
        IncidentEntity incident = incidentAt(from);

        if (allowed) {
            incident.transitionTo(to, CHANGED);
            assertThat(incident.getStatus()).isEqualTo(to);
            assertThat(incident.getUpdatedAt()).isEqualTo(CHANGED);
        } else {
            assertThatThrownBy(() -> incident.transitionTo(to, CHANGED))
                    .isInstanceOf(InvalidIncidentTransitionException.class);
        }
    }

    @Test
    void resolutionAndReopenMaintainCurrentLifecycleTimestamps() {
        IncidentEntity incident = incidentAt(IncidentStatus.INVESTIGATING);

        incident.transitionTo(IncidentStatus.RESOLVED, CHANGED);
        assertThat(incident.getResolvedAt()).isEqualTo(CHANGED);
        assertThat(incident.getClosedAt()).isNull();

        Instant reopened = CHANGED.plusSeconds(60);
        incident.transitionTo(IncidentStatus.INVESTIGATING, reopened);
        assertThat(incident.getResolvedAt()).isNull();
        assertThat(incident.getClosedAt()).isNull();
    }

    @Test
    void closingSetsClosedTimestamp() {
        IncidentEntity incident = incidentAt(IncidentStatus.RESOLVED);
        incident.transitionTo(IncidentStatus.CLOSED, CHANGED);

        assertThat(incident.getClosedAt()).isEqualTo(CHANGED);
        assertThat(incident.getResolvedAt()).isNotNull();
    }

    private static Stream<Arguments> transitionMatrix() {
        return Stream.of(IncidentStatus.values())
                .flatMap(from -> Stream.of(IncidentStatus.values())
                        .map(to -> Arguments.of(from, to, from.canTransitionTo(to))));
    }

    private static IncidentEntity incidentAt(IncidentStatus target) {
        IncidentEntity incident = IncidentEntity.create(
                UUID.randomUUID(), "Test", null, IncidentSeverity.HIGH, null, Set.of(), CREATED);
        switch (target) {
            case OPEN -> { }
            case INVESTIGATING -> incident.transitionTo(IncidentStatus.INVESTIGATING, CREATED.plusSeconds(1));
            case MITIGATED -> {
                incident.transitionTo(IncidentStatus.INVESTIGATING, CREATED.plusSeconds(1));
                incident.transitionTo(IncidentStatus.MITIGATED, CREATED.plusSeconds(2));
            }
            case RESOLVED -> incident.transitionTo(IncidentStatus.RESOLVED, CREATED.plusSeconds(1));
            case CLOSED -> {
                incident.transitionTo(IncidentStatus.RESOLVED, CREATED.plusSeconds(1));
                incident.transitionTo(IncidentStatus.CLOSED, CREATED.plusSeconds(2));
            }
        }
        return incident;
    }
}
