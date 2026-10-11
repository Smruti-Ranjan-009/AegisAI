package com.aegisai.incident.client;

import com.aegisai.incident.dto.SignalSummaryRequest;
import com.fasterxml.jackson.databind.JsonNode;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class RagServiceClient {
    private final RestClient client;

    public RagServiceClient(
            RestClient.Builder builder,
            @Value("${aegis.intelligence.rag-base-url}") String baseUrl,
            @Value("${aegis.intelligence.rag-connect-timeout}") Duration connectTimeout,
            @Value("${aegis.intelligence.rag-read-timeout}") Duration readTimeout) {
        HttpClient httpClient = HttpClient.newBuilder().connectTimeout(connectTimeout).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(readTimeout);
        this.client = builder.clone().baseUrl(baseUrl).requestFactory(factory).build();
    }

    public RagDiagnosisResponse diagnose(RagDiagnosisRequest request, String correlationId) {
        try {
            RagDiagnosisResponse response = client.post()
                    .uri("/api/v1/diagnose")
                    .header("X-Correlation-ID", correlationId)
                    .body(request)
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, (req, result) -> {
                        boolean validationFailure = result.getStatusCode().value() == 422;
                        throw new UpstreamServiceException(
                                validationFailure
                                        ? "RAG_VALIDATION_FAILED"
                                        : result.getStatusCode().is5xxServerError()
                                            ? "RAG_SERVICE_UNAVAILABLE" : "RAG_GENERATION_FAILED",
                                "RAG service rejected the diagnosis request",
                                validationFailure,
                                null);
                    })
                    .body(RagDiagnosisResponse.class);
            validate(response, correlationId);
            return response;
        } catch (UpstreamServiceException exception) {
            throw exception;
        } catch (RestClientException exception) {
            throw new UpstreamServiceException(
                    "RAG_SERVICE_UNAVAILABLE", "RAG service is unavailable", false, exception);
        }
    }

    private static void validate(RagDiagnosisResponse response, String correlationId) {
        if (response == null
                || !"rag_diagnosis_result_v1".equals(response.schemaVersion())
                || !"incident_query_v1".equals(response.queryVersion())
                || !response.advisory()
                || !response.requiresHumanReview()
                || !correlationId.equals(response.correlationId())
                || !("grounded".equals(response.status())
                    || "insufficient_evidence".equals(response.status()))) {
            throw invalid("RAG response contract or correlation ID is invalid");
        }
        Set<String> evidenceIds = new HashSet<>();
        response.evidence().forEach(item -> evidenceIds.add(item.path("evidence_id").asText()));
        Set<String> claimIds = new HashSet<>();
        response.suspectedCauses().forEach(item -> item.path("evidence").forEach(id -> claimIds.add(id.asText())));
        response.recommendedActions().forEach(item -> item.path("evidence").forEach(id -> claimIds.add(id.asText())));
        Set<String> citationIds = new HashSet<>();
        response.citations().forEach(item -> citationIds.add(item.path("evidence_id").asText()));
        if ("insufficient_evidence".equals(response.status())) {
            if (!claimIds.isEmpty() || !citationIds.isEmpty()) {
                throw invalid("insufficient-evidence response contains claims or citations");
            }
        } else if (claimIds.isEmpty()
                || !citationIds.equals(claimIds)
                || !evidenceIds.containsAll(citationIds)) {
            throw invalid("RAG citations do not exactly cover grounded claim evidence");
        }
    }

    private static UpstreamServiceException invalid(String message) {
        return new UpstreamServiceException("RAG_VALIDATION_FAILED", message, true, null);
    }

    public record RagDiagnosisRequest(
            String schemaVersion,
            String incidentId,
            String title,
            String description,
            List<String> affectedServices,
            JsonNode anomaly,
            JsonNode classification,
            List<SignalSummaryRequest> signalSummary) {
    }

    public record RagDiagnosisResponse(
            String schemaVersion,
            String queryVersion,
            String status,
            boolean advisory,
            boolean requiresHumanReview,
            String summary,
            List<JsonNode> suspectedCauses,
            List<JsonNode> recommendedActions,
            List<JsonNode> citations,
            List<JsonNode> evidence,
            JsonNode lineage,
            JsonNode timingsMs,
            String correlationId) {
    }
}
