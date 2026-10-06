CREATE TABLE incident_timeline (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    message TEXT NOT NULL,
    actor VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_incident_timeline_event_type
        CHECK (event_type IN (
            'CREATED',
            'DETAILS_UPDATED',
            'STATUS_CHANGED',
            'NOTE_ADDED',
            'ROOT_CAUSE_UPDATED',
            'REMEDIATION_UPDATED'
        )),
    CONSTRAINT fk_timeline_incident
        FOREIGN KEY (incident_id) REFERENCES incidents (id) ON DELETE CASCADE
);
