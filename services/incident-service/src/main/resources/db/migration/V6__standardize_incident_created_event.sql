ALTER TABLE incident_timeline_entries
    DROP CONSTRAINT ck_incident_timeline_entries_event_type;

UPDATE incident_timeline_entries
SET event_type = 'INCIDENT_CREATED'
WHERE event_type = 'CREATED';

ALTER TABLE incident_timeline_entries
    ADD CONSTRAINT ck_incident_timeline_entries_event_type
        CHECK (event_type IN (
            'INCIDENT_CREATED',
            'DETAILS_UPDATED',
            'STATUS_CHANGED',
            'NOTE_ADDED',
            'ROOT_CAUSE_UPDATED',
            'REMEDIATION_UPDATED'
        ));
