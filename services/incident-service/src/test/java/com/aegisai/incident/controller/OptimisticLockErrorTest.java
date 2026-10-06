package com.aegisai.incident.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aegisai.incident.service.IncidentService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(IncidentController.class)
class OptimisticLockErrorTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private IncidentService incidentService;

    @Test
    void optimisticLockingFailureMapsToConflictProblem() throws Exception {
        UUID incidentId = UUID.randomUUID();
        when(incidentService.update(eq(incidentId), any()))
                .thenThrow(new OptimisticLockingFailureException("stale version"));

        mockMvc.perform(patch("/api/v1/incidents/{id}", incidentId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"owner":"new-owner"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("optimistic_lock_conflict"))
                .andExpect(jsonPath("$.detail").value(
                        "The incident was updated by another request. Reload it and retry."));
    }
}
