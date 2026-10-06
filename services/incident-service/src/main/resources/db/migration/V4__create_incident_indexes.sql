CREATE INDEX idx_incidents_created_at ON incidents (created_at DESC);
CREATE INDEX idx_incidents_status_created_at ON incidents (status, created_at DESC);
CREATE INDEX idx_incidents_severity_created_at ON incidents (severity, created_at DESC);
CREATE INDEX idx_incidents_owner ON incidents (owner);
CREATE INDEX idx_affected_services_service ON incident_affected_services (service_name, incident_id);
CREATE INDEX idx_timeline_incident_created ON incident_timeline (incident_id, created_at, id);
