package com.aegisai.incident.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aegisai.incident.PostgreSqlIntegrationTest;
import com.aegisai.incident.repository.IncidentRepository;
import com.aegisai.incident.repository.TimelineEntryRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class IncidentApiIntegrationTest extends PostgreSqlIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private TimelineEntryRepository timelineRepository;

    @Autowired
    private IncidentRepository incidentRepository;

    @BeforeEach
    void cleanDatabase() {
        timelineRepository.deleteAll();
        incidentRepository.deleteAll();
    }

    @Test
    void createReadUpdateAndTimelineFlow() throws Exception {
        UUID id = createIncident("Checkout latency", "HIGH", "payments", "checkout-service");

        mockMvc.perform(get("/api/v1/incidents/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id.toString()))
                .andExpect(jsonPath("$.status").value("OPEN"))
                .andExpect(jsonPath("$.affected_services[0]").value("checkout-service"))
                .andExpect(jsonPath("$.version").isNumber());

        mockMvc.perform(patch("/api/v1/incidents/{id}", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "severity": "CRITICAL",
                                  "owner": "incident-command",
                                  "root_cause": "Exhausted connection pool",
                                  "remediation": "Increase pool and reduce timeout"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.severity").value("CRITICAL"))
                .andExpect(jsonPath("$.owner").value("incident-command"))
                .andExpect(jsonPath("$.root_cause").value("Exhausted connection pool"))
                .andExpect(jsonPath("$.version").isNumber());

        mockMvc.perform(post("/api/v1/incidents/{id}/timeline", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"message":"Database team engaged","actor":"on-call"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.event_type").value("NOTE_ADDED"));

        mockMvc.perform(get("/api/v1/incidents/{id}/timeline", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_elements").value(5))
                .andExpect(jsonPath("$.content[0].event_type").value("INCIDENT_CREATED"))
                .andExpect(jsonPath("$.content[4].event_type").value("NOTE_ADDED"));
    }

    @Test
    void listSupportsFiltersAndPagination() throws Exception {
        UUID checkout = createIncident("Checkout issue", "HIGH", "payments", "checkout-service");
        createIncident("Search issue", "LOW", "search", "search-service");

        mockMvc.perform(post("/api/v1/incidents/{id}/transition", checkout)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"target_status":"INVESTIGATING","actor":"on-call"}
                                """))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/v1/incidents")
                        .param("status", "INVESTIGATING")
                        .param("severity", "HIGH")
                        .param("service", "CHECKOUT-SERVICE")
                        .param("owner", "PAYMENTS")
                        .param("page", "0")
                        .param("size", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_elements").value(1))
                .andExpect(jsonPath("$.content[0].id").value(checkout.toString()));
    }

    @Test
    void transitionRulesAndLifecycleTimestampsAreVisibleThroughApi() throws Exception {
        UUID id = createIncident("Lifecycle", "MEDIUM", null, "api-service");

        mockMvc.perform(post("/api/v1/incidents/{id}/transition", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"target_status":"MITIGATED"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("invalid_incident_transition"));

        mockMvc.perform(post("/api/v1/incidents/{id}/transition", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"target_status":"RESOLVED","note":"Recovered"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("RESOLVED"))
                .andExpect(jsonPath("$.resolved_at").isNotEmpty());

        mockMvc.perform(post("/api/v1/incidents/{id}/transition", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"target_status":"INVESTIGATING","note":"Regression"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.resolved_at").doesNotExist());
    }

    @Test
    void validationNotFoundAndUnknownFieldsUseStructuredProblems() throws Exception {
        mockMvc.perform(post("/api/v1/incidents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":" ","severity":"HIGH"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("validation_failed"))
                .andExpect(jsonPath("$.field_errors.title").exists());

        mockMvc.perform(post("/api/v1/incidents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Invalid severity","severity":"URGENT"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("validation_failed"));

        mockMvc.perform(post("/api/v1/incidents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":%s,"severity":"LOW"}
                                """.formatted(objectMapper.writeValueAsString("x".repeat(201)))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.field_errors.title").exists());

        mockMvc.perform(get("/api/v1/incidents/{id}", UUID.randomUUID()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error_code").value("incident_not_found"));

        UUID id = createIncident("Protected fields", "LOW", null, "api-service");
        mockMvc.perform(patch("/api/v1/incidents/{id}", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"CLOSED"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("validation_failed"));

        mockMvc.perform(patch("/api/v1/incidents/{id}", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"affected_services":[null]}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.field_errors").isNotEmpty());
    }

    private UUID createIncident(String title, String severity, String owner, String service) throws Exception {
        String ownerJson = owner == null ? "null" : objectMapper.writeValueAsString(owner);
        String body = """
                {
                  "title": %s,
                  "description": "Test incident",
                  "severity": %s,
                  "owner": %s,
                  "affected_services": [%s]
                }
                """.formatted(
                objectMapper.writeValueAsString(title),
                objectMapper.writeValueAsString(severity),
                ownerJson,
                objectMapper.writeValueAsString(service));
        MvcResult result = mockMvc.perform(post("/api/v1/incidents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", org.hamcrest.Matchers.containsString("/api/v1/incidents/")))
                .andReturn();
        JsonNode response = objectMapper.readTree(result.getResponse().getContentAsString());
        return UUID.fromString(response.get("id").asText());
    }
}
