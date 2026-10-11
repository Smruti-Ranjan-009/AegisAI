package com.aegisai.incident.client;

import com.aegisai.incident.dto.FeatureWindowRequest;
import com.fasterxml.jackson.databind.JsonNode;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class MlServiceClient {
    private final RestClient client;

    public MlServiceClient(
            RestClient.Builder builder,
            @Value("${aegis.intelligence.ml-base-url}") String baseUrl,
            @Value("${aegis.intelligence.ml-connect-timeout}") Duration connectTimeout,
            @Value("${aegis.intelligence.ml-read-timeout}") Duration readTimeout) {
        HttpClient httpClient = HttpClient.newBuilder().connectTimeout(connectTimeout).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(readTimeout);
        this.client = builder.clone().baseUrl(baseUrl).requestFactory(factory).build();
    }

    public MlInferenceResponse analyze(MlInferenceRequest request, String correlationId) {
        try {
            MlInferenceResponse response = client.post()
                    .uri("/api/v1/inference/analyze")
                    .header("X-Correlation-ID", correlationId)
                    .body(request)
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, (req, result) -> {
                        throw new UpstreamServiceException(
                                result.getStatusCode().is5xxServerError()
                                        ? "ML_SERVICE_UNAVAILABLE" : "ML_INFERENCE_FAILED",
                                "ML service rejected the inference request",
                                false,
                                null);
                    })
                    .body(MlInferenceResponse.class);
            if (response == null || !"ml_inference_result_v1".equals(response.schemaVersion())) {
                throw new UpstreamServiceException(
                        "ML_INFERENCE_FAILED", "ML service returned an invalid contract", true, null);
            }
            return response;
        } catch (UpstreamServiceException exception) {
            throw exception;
        } catch (RestClientException exception) {
            throw new UpstreamServiceException(
                    "ML_SERVICE_UNAVAILABLE", "ML service is unavailable", false, exception);
        }
    }

    public record MlInferenceRequest(
            String schemaVersion,
            int featureSchemaVersion,
            String inputId,
            List<String> featureNames,
            List<FeatureWindowRequest> windows) {
    }

    public record MlInferenceResponse(
            String schemaVersion,
            String inputId,
            String analysisStatus,
            JsonNode anomaly,
            JsonNode classification,
            JsonNode lineage,
            JsonNode timingsMs,
            String correlationId) {
    }
}

