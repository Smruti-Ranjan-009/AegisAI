CREATE TABLE incident_intelligence_runs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(40) NOT NULL,
    schema_version VARCHAR(40) NOT NULL,
    input_id VARCHAR(200) NOT NULL,
    correlation_id VARCHAR(200) NOT NULL,
    requires_human_review BOOLEAN NOT NULL DEFAULT TRUE,
    ml_result JSONB,
    intelligence_result JSONB,
    lineage JSONB,
    timings JSONB,
    failure_code VARCHAR(80),
    failure_message TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_intelligence_run_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    CONSTRAINT uq_intelligence_run_request UNIQUE (incident_id, request_hash),
    CONSTRAINT ck_intelligence_run_status CHECK (status IN (
        'PENDING', 'RUNNING', 'NO_ANOMALY_SIGNAL', 'GROUNDED_ADVISORY',
        'INSUFFICIENT_EVIDENCE', 'FAILED_ML', 'FAILED_RAG', 'FAILED_VALIDATION'
    )),
    CONSTRAINT ck_intelligence_human_review CHECK (requires_human_review)
);

CREATE INDEX idx_intelligence_run_incident_created
    ON incident_intelligence_runs (incident_id, created_at DESC, id DESC);
CREATE INDEX idx_intelligence_run_status
    ON incident_intelligence_runs (status);

ALTER TABLE incident_timeline_entries
    DROP CONSTRAINT ck_incident_timeline_entries_event_type;

ALTER TABLE incident_timeline_entries
    ADD CONSTRAINT ck_incident_timeline_entries_event_type
        CHECK (event_type IN (
            'INCIDENT_CREATED', 'DETAILS_UPDATED', 'STATUS_CHANGED', 'NOTE_ADDED',
            'ROOT_CAUSE_UPDATED', 'REMEDIATION_UPDATED', 'INTELLIGENCE_STARTED',
            'ANOMALY_NOT_DETECTED', 'INTELLIGENCE_GROUNDED',
            'INTELLIGENCE_ABSTAINED', 'INTELLIGENCE_FAILED'
        ));

