CREATE TABLE incident_affected_services (
    incident_id UUID NOT NULL,
    service_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (incident_id, service_name),
    CONSTRAINT fk_affected_services_incident
        FOREIGN KEY (incident_id) REFERENCES incidents (id) ON DELETE CASCADE
);
