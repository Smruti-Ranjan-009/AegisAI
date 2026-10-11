package com.aegisai.incident.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aegisai.incident.PostgreSqlIntegrationTest;
import com.aegisai.incident.repository.IncidentRepository;
import com.aegisai.incident.repository.IntelligenceRunRepository;
import com.aegisai.incident.repository.TimelineEntryRepository;
import com.aegisai.incident.service.FrozenFeatureContract;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class IntelligenceApiIntegrationTest extends PostgreSqlIntegrationTest {
    private static final HttpServer ML_SERVER = server(IntelligenceApiIntegrationTest::ml);
    private static final HttpServer RAG_SERVER = server(IntelligenceApiIntegrationTest::rag);
    private static final AtomicReference<String> MODE = new AtomicReference<>("grounded");
    private static final AtomicInteger ML_CALLS = new AtomicInteger();
    private static final AtomicInteger RAG_CALLS = new AtomicInteger();
    private static final AtomicReference<String> ML_CORRELATION = new AtomicReference<>();
    private static final AtomicReference<String> RAG_CORRELATION = new AtomicReference<>();
    private static final AtomicReference<String> ML_REQUEST_BODY = new AtomicReference<>();

    @Autowired private MockMvc mockMvc;
    @Autowired private ObjectMapper objectMapper;
    @Autowired private IntelligenceRunRepository runRepository;
    @Autowired private TimelineEntryRepository timelineRepository;
    @Autowired private IncidentRepository incidentRepository;

    @DynamicPropertySource
    static void serviceProperties(DynamicPropertyRegistry registry) {
        registry.add("aegis.intelligence.ml-base-url", () -> url(ML_SERVER));
        registry.add("aegis.intelligence.rag-base-url", () -> url(RAG_SERVER));
    }

    @BeforeEach
    void clean() {
        runRepository.deleteAll();
        timelineRepository.deleteAll();
        incidentRepository.deleteAll();
        MODE.set("grounded");
        ML_CALLS.set(0);
        RAG_CALLS.set(0);
        ML_CORRELATION.set(null);
        RAG_CORRELATION.set(null);
        ML_REQUEST_BODY.set(null);
    }

    @AfterAll
    static void stopServers() {
        ML_SERVER.stop(0);
        RAG_SERVER.stop(0);
    }

    @Test
    void groundedFlowPersistsLineageTimelineCorrelationAndIdempotentReplay() throws Exception {
        UUID incidentId = createIncident();
        MvcResult first = submit(incidentId, request("input-1", 1.0), "phase12-test-123", 201);
        JsonNode body = objectMapper.readTree(first.getResponse().getContentAsString());
        String runId = body.path("run_id").asText();
        assertThat(body.path("status").asText()).isEqualTo("GROUNDED_ADVISORY");
        assertThat(body.path("requires_human_review").asBoolean()).isTrue();
        assertThat(body.path("lineage").path("rag").path("prompt_version").asText())
                .isEqualTo("grounded_incident_v1");

        MvcResult replay = submit(incidentId, request("input-1", 1.0), "different-correlation", 200);
        assertThat(objectMapper.readTree(replay.getResponse().getContentAsString())
                .path("run_id").asText()).isEqualTo(runId);
        assertThat(ML_CALLS).hasValue(1);
        assertThat(RAG_CALLS).hasValue(1);
        assertThat(ML_CORRELATION).hasValue("phase12-test-123");
        assertThat(RAG_CORRELATION).hasValue("phase12-test-123");
        JsonNode serializedMlRequest = objectMapper.readTree(ML_REQUEST_BODY.get());
        assertThat(serializedMlRequest.path("windows").get(0).has("valid_window")).isFalse();
        assertThat(serializedMlRequest.path("windows").get(0).path("window_id").asText())
                .isEqualTo("window-1");

        mockMvc.perform(get("/api/v1/incidents/{id}/intelligence-runs/{runId}", incidentId, runId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("GROUNDED_ADVISORY"));
        mockMvc.perform(get("/api/v1/incidents/{id}/intelligence-runs", incidentId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_elements").value(1));
        mockMvc.perform(get("/api/v1/incidents/{id}/timeline", incidentId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[1].event_type").value("INTELLIGENCE_STARTED"))
                .andExpect(jsonPath("$.content[2].event_type").value("INTELLIGENCE_GROUNDED"));
    }

    @Test
    void noAnomalySkipsRagAndChangedInputCreatesNewRun() throws Exception {
        MODE.set("no_anomaly");
        UUID incidentId = createIncident();
        submit(incidentId, request("input-normal-1", 0.1), null, 201)
                .getResponse().getContentAsString();
        submit(incidentId, request("input-normal-2", 0.2), null, 201);
        assertThat(RAG_CALLS).hasValue(0);
        assertThat(ML_CALLS).hasValue(2);
        assertThat(runRepository.count()).isEqualTo(2);
        assertThat(runRepository.findAll())
                .allMatch(run -> run.getStatus().name().equals("NO_ANOMALY_SIGNAL"));
    }

    @Test
    void insufficientEvidenceIsPersistedAsAbstention() throws Exception {
        MODE.set("insufficient");
        UUID incidentId = createIncident();
        MvcResult result = submit(incidentId, request("input-abstain", 1.0), null, 201);
        JsonNode body = objectMapper.readTree(result.getResponse().getContentAsString());
        assertThat(body.path("status").asText()).isEqualTo("INSUFFICIENT_EVIDENCE");
        assertThat(body.path("requires_human_review").asBoolean()).isTrue();
        assertThat(body.path("intelligence").path("suspected_causes").isEmpty()).isTrue();
    }

    @Test
    void dependencyAndValidationFailuresPersistExplicitStates() throws Exception {
        UUID incidentId = createIncident();
        MODE.set("ml_failure");
        JsonNode ml = body(submit(incidentId, request("input-ml-fail", 1), null, 201));
        assertThat(ml.path("status").asText()).isEqualTo("FAILED_ML");
        assertThat(RAG_CALLS).hasValue(0);

        MODE.set("rag_failure");
        JsonNode rag = body(submit(incidentId, request("input-rag-fail", 1), null, 201));
        assertThat(rag.path("status").asText()).isEqualTo("FAILED_RAG");
        assertThat(rag.path("ml").isObject()).isTrue();

        MODE.set("invalid_rag");
        JsonNode invalid = body(submit(incidentId, request("input-invalid", 1), null, 201));
        assertThat(invalid.path("status").asText()).isEqualTo("FAILED_VALIDATION");
        assertThat(invalid.path("failure_code").asText()).isEqualTo("RAG_VALIDATION_FAILED");

        MODE.set("rag_validation_failure");
        JsonNode rejected = body(submit(incidentId, request("input-rejected", 1), null, 201));
        assertThat(rejected.path("status").asText()).isEqualTo("FAILED_VALIDATION");
        assertThat(rejected.path("failure_code").asText()).isEqualTo("RAG_VALIDATION_FAILED");
    }

    @Test
    void concurrentDuplicateRequestsClaimOneRowAndInvokeGenerationOnce() throws Exception {
        UUID incidentId = createIncident();
        String content = request("input-concurrent", 1.0);
        int callers = 6;
        CountDownLatch ready = new CountDownLatch(callers);
        CountDownLatch start = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(callers);
        try {
            var futures = new ArrayList<java.util.concurrent.Future<String>>();
            for (int index = 0; index < callers; index++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await(5, TimeUnit.SECONDS);
                    MvcResult result = submitAnySuccess(
                            incidentId, content, "phase12-concurrent");
                    return body(result).path("run_id").asText();
                }));
            }
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            var runIds = new java.util.HashSet<String>();
            for (var future : futures) {
                runIds.add(future.get(15, TimeUnit.SECONDS));
            }
            assertThat(runIds).hasSize(1);
        } finally {
            executor.shutdownNow();
        }
        assertThat(runRepository.count()).isEqualTo(1);
        assertThat(ML_CALLS).hasValue(1);
        assertThat(RAG_CALLS).hasValue(1);
    }

    private MvcResult submitAnySuccess(UUID incidentId, String content, String correlation)
            throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/incidents/{id}/intelligence-runs", incidentId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Correlation-ID", correlation)
                        .content(content))
                .andExpect(status().is2xxSuccessful())
                .andReturn();
        return result;
    }

    private MvcResult submit(UUID incidentId, String content, String correlation, int statusCode)
            throws Exception {
        var builder = post("/api/v1/incidents/{id}/intelligence-runs", incidentId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(content);
        if (correlation != null) {
            builder.header("X-Correlation-ID", correlation);
        }
        return mockMvc.perform(builder)
                .andExpect(status().is(statusCode))
                .andExpect(header().exists("X-Correlation-ID"))
                .andReturn();
    }

    private JsonNode body(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsString());
    }

    private UUID createIncident() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/incidents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Checkout issue","description":"Latency increased",
                                 "severity":"HIGH","affected_services":["checkout"]}
                                """))
                .andExpect(status().isCreated()).andReturn();
        return UUID.fromString(body(result).path("id").asText());
    }

    private String request(String inputId, double value) throws Exception {
        List<String> names = new ArrayList<>();
        List<Double> values = new ArrayList<>();
        for (int index = 0; index < FrozenFeatureContract.FEATURE_NAMES.size(); index++) {
            names.add(FrozenFeatureContract.FEATURE_NAMES.get(index));
            values.add(index == 0 ? value : 0.0);
        }
        var root = objectMapper.createObjectNode();
        root.put("schema_version", "intelligence_v1");
        root.put("input_id", inputId);
        root.put("feature_schema_version", 1);
        root.set("feature_names", objectMapper.valueToTree(names));
        var window = objectMapper.createObjectNode();
        window.put("window_id", "window-1");
        window.put("service_name", "checkout");
        window.put("window_start_utc", "2026-01-01T00:00:00Z");
        window.put("window_end_utc", "2026-01-01T00:01:00Z");
        window.set("values", objectMapper.valueToTree(values));
        root.set("windows", objectMapper.createArrayNode().add(window));
        root.set("signal_summary", objectMapper.createArrayNode());
        return objectMapper.writeValueAsString(root);
    }

    private static HttpServer server(ThrowingHandler handler) {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                try {
                    handler.handle(exchange);
                } catch (Exception exception) {
                    exchange.sendResponseHeaders(500, -1);
                } finally {
                    exchange.close();
                }
            });
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static String url(HttpServer server) {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    private static void ml(HttpExchange exchange) throws IOException {
        ML_CALLS.incrementAndGet();
        ML_CORRELATION.set(exchange.getRequestHeaders().getFirst("X-Correlation-ID"));
        ML_REQUEST_BODY.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
        if (MODE.get().equals("ml_failure")) {
            reply(exchange, 503, "{}");
            return;
        }
        boolean anomaly = !MODE.get().equals("no_anomaly");
        String classification = anomaly ? """
                {"model":{"name":"AegisAI-IncidentClassifier","model_id":"fake-classifier-v1","source":"fake"},
                 "predicted_incident_type":"dependency_failure","class_probabilities":{"cpu_saturation":0.05,"memory_leak":0.05,"service_failure":0.05,"dependency_failure":0.8,"high_latency":0.05}}
                """ : "null";
        reply(exchange, 200, """
                {"schema_version":"ml_inference_result_v1","input_id":"input",
                 "analysis_status":"%s","anomaly":{"model":{"name":"AegisAI-AnomalyDetector","model_id":"fake-anomaly-v1","source":"fake"},"threshold":0.5,"score":%s,"is_anomaly":%s,"windows":[]},
                 "classification":%s,"lineage":{"feature_schema_version":1},
                 "timings_ms":{"ml_service_ms":2.0},"correlation_id":"%s"}
                """.formatted(anomaly ? "anomaly_detected" : "no_anomaly_signal",
                anomaly ? "0.9" : "0.1", anomaly, classification, ML_CORRELATION.get()));
    }

    private static void rag(HttpExchange exchange) throws IOException {
        RAG_CALLS.incrementAndGet();
        RAG_CORRELATION.set(exchange.getRequestHeaders().getFirst("X-Correlation-ID"));
        if (MODE.get().equals("rag_failure")) {
            reply(exchange, 503, "{}");
            return;
        }
        if (MODE.get().equals("rag_validation_failure")) {
            reply(exchange, 422, "{\"detail\":{\"code\":\"RAG_VALIDATION_FAILED\"}}");
            return;
        }
        boolean insufficient = MODE.get().equals("insufficient");
        boolean invalid = MODE.get().equals("invalid_rag");
        String claims = insufficient ? "[]" : "[{\"cause\":\"Possible dependency pressure\",\"evidence\":[\"E1\"]}]";
        String actions = insufficient ? "[]" : "[{\"action\":\"Validate dependency health\",\"evidence\":[\"E1\"]}]";
        String citations = insufficient ? "[]" : invalid ? "[]" : "[{\"evidence_id\":\"E1\",\"source_path\":\"runbooks/dependency.md\",\"heading_path\":[\"Triage\"]}]";
        String evidence = insufficient ? "[]" : "[{\"evidence_id\":\"E1\",\"chunk_id\":\"chunk-1\",\"source_path\":\"runbooks/dependency.md\",\"heading_path\":[\"Triage\"],\"retrieval_rank\":1,\"reranked_rank\":1}]";
        reply(exchange, 200, """
                {"schema_version":"rag_diagnosis_result_v1","query_version":"incident_query_v1",
                 "status":"%s","advisory":true,"requires_human_review":true,
                 "summary":"Advisory only","suspected_causes":%s,"recommended_actions":%s,
                 "citations":%s,"evidence":%s,"lineage":{"corpus_fingerprint":"fake","prompt_version":"grounded_incident_v1"},
                 "timings_ms":{"rag_service_ms":3.0},"correlation_id":"%s"}
                """.formatted(insufficient ? "insufficient_evidence" : "grounded",
                claims, actions, citations, evidence, RAG_CORRELATION.get()));
    }

    private static void reply(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    @FunctionalInterface
    private interface ThrowingHandler {
        void handle(HttpExchange exchange) throws Exception;
    }
}
