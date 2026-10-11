package com.aegisai.incident.service;

import com.aegisai.incident.client.MlServiceClient;
import com.aegisai.incident.client.MlServiceClient.MlInferenceRequest;
import com.aegisai.incident.client.MlServiceClient.MlInferenceResponse;
import com.aegisai.incident.client.RagServiceClient;
import com.aegisai.incident.client.RagServiceClient.RagDiagnosisRequest;
import com.aegisai.incident.client.RagServiceClient.RagDiagnosisResponse;
import com.aegisai.incident.client.UpstreamServiceException;
import com.aegisai.incident.domain.IncidentEntity;
import com.aegisai.incident.domain.IntelligenceRunEntity;
import com.aegisai.incident.domain.IntelligenceRunStatus;
import com.aegisai.incident.dto.IntelligenceRunRequest;
import com.aegisai.incident.dto.IntelligenceRunResponse;
import com.aegisai.incident.dto.PageResponse;
import com.aegisai.incident.exception.IncidentNotFoundException;
import com.aegisai.incident.exception.IntelligenceRunNotFoundException;
import com.aegisai.incident.repository.IncidentRepository;
import com.aegisai.incident.repository.IntelligenceRunRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IntelligenceService {
    private static final Logger LOGGER = LoggerFactory.getLogger(IntelligenceService.class);

    private final IncidentRepository incidentRepository;
    private final IntelligenceRunRepository runRepository;
    private final IntelligenceRunStore store;
    private final MlServiceClient mlClient;
    private final RagServiceClient ragClient;
    private final ObjectMapper objectMapper;

    public IntelligenceService(
            IncidentRepository incidentRepository,
            IntelligenceRunRepository runRepository,
            IntelligenceRunStore store,
            MlServiceClient mlClient,
            RagServiceClient ragClient,
            ObjectMapper objectMapper) {
        this.incidentRepository = incidentRepository;
        this.runRepository = runRepository;
        this.store = store;
        this.mlClient = mlClient;
        this.ragClient = ragClient;
        this.objectMapper = objectMapper;
    }

    public RunResult run(UUID incidentId, IntelligenceRunRequest request, String suppliedCorrelationId) {
        IncidentEntity incident = incidentRepository.findWithAffectedServicesById(incidentId)
                .orElseThrow(() -> new IncidentNotFoundException(incidentId));
        validateRequest(request);
        String correlationId = suppliedCorrelationId == null || suppliedCorrelationId.isBlank()
                ? UUID.randomUUID().toString() : suppliedCorrelationId.strip();
        String requestHash = fingerprint(incidentId, request);
        IntelligenceRunStore.ClaimResult claim = store.claim(
                incidentId, requestHash, request.schemaVersion(), request.inputId(), correlationId);
        if (!claim.claimed()) {
            return new RunResult(toResponse(claim.entity()), false);
        }
        UUID runId = claim.entity().getId();
        store.markRunning(incidentId, runId);
        long started = System.nanoTime();
        MlInferenceResponse ml;
        try {
            ml = mlClient.analyze(new MlInferenceRequest(
                    "ml_inference_v1", request.featureSchemaVersion(), request.inputId(),
                    request.featureNames(), request.windows()), correlationId);
        } catch (UpstreamServiceException exception) {
            IntelligenceRunEntity failed = store.fail(
                    incidentId, runId, IntelligenceRunStatus.FAILED_ML,
                    exception.getCode(), exception.getMessage(), null, null,
                    timings(started, null, null));
            return new RunResult(toResponse(failed), true);
        }
        JsonNode mlNode = objectMapper.valueToTree(ml);
        if ("no_anomaly_signal".equals(ml.analysisStatus())) {
            IntelligenceRunEntity completed = store.complete(
                    incidentId, runId, IntelligenceRunStatus.NO_ANOMALY_SIGNAL,
                    mlNode, null, combinedLineage(ml.lineage(), null),
                    timings(started, ml.timingsMs(), null));
            return new RunResult(toResponse(completed), true);
        }
        if (!"anomaly_detected".equals(ml.analysisStatus()) || ml.classification() == null) {
            IntelligenceRunEntity failed = store.fail(
                    incidentId, runId, IntelligenceRunStatus.FAILED_VALIDATION,
                    "ML_INFERENCE_FAILED", "ML response omitted anomaly classification",
                    mlNode, combinedLineage(ml.lineage(), null), timings(started, ml.timingsMs(), null));
            return new RunResult(toResponse(failed), true);
        }
        RagDiagnosisResponse rag;
        try {
            rag = ragClient.diagnose(ragRequest(incident, request, ml), correlationId);
        } catch (UpstreamServiceException exception) {
            IntelligenceRunStatus status = exception.isValidationFailure()
                    ? IntelligenceRunStatus.FAILED_VALIDATION : IntelligenceRunStatus.FAILED_RAG;
            IntelligenceRunEntity failed = store.fail(
                    incidentId, runId, status, exception.getCode(), exception.getMessage(),
                    mlNode, combinedLineage(ml.lineage(), null), timings(started, ml.timingsMs(), null));
            return new RunResult(toResponse(failed), true);
        }
        IntelligenceRunStatus status = "grounded".equals(rag.status())
                ? IntelligenceRunStatus.GROUNDED_ADVISORY
                : IntelligenceRunStatus.INSUFFICIENT_EVIDENCE;
        JsonNode ragNode = objectMapper.valueToTree(rag);
        IntelligenceRunEntity completed = store.complete(
                incidentId, runId, status, mlNode, ragNode,
                combinedLineage(ml.lineage(), rag.lineage()),
                timings(started, ml.timingsMs(), rag.timingsMs()));
        LOGGER.info(
                "intelligence_run correlation_id={} incident_id={} intelligence_run_id={} status={} overall_ms={}",
                correlationId, incidentId, runId, status, (System.nanoTime() - started) / 1_000_000.0);
        return new RunResult(toResponse(completed), true);
    }

    @Transactional(readOnly = true)
    public IntelligenceRunResponse get(UUID incidentId, UUID runId) {
        assertIncident(incidentId);
        return toResponse(runRepository.findByIdAndIncidentId(runId, incidentId)
                .orElseThrow(() -> new IntelligenceRunNotFoundException(incidentId, runId)));
    }

    @Transactional(readOnly = true)
    public PageResponse<IntelligenceRunResponse> list(UUID incidentId, int page, int size) {
        assertIncident(incidentId);
        PageRequest pageable = PageRequest.of(
                page, size, Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
        return PageResponse.from(runRepository.findByIncidentId(incidentId, pageable).map(this::toResponse));
    }

    private RagDiagnosisRequest ragRequest(
            IncidentEntity incident, IntelligenceRunRequest request, MlInferenceResponse ml) {
        ObjectNode anomaly = objectMapper.createObjectNode();
        anomaly.put("anomaly_score", ml.anomaly().path("score").asDouble());
        anomaly.put("threshold", ml.anomaly().path("threshold").asDouble());
        anomaly.put("is_anomaly", true);
        anomaly.put("model_id", ml.anomaly().path("model").path("model_id").asText());
        ObjectNode classification = objectMapper.createObjectNode();
        classification.put(
                "predicted_incident_type",
                ml.classification().path("predicted_incident_type").asText());
        classification.set(
                "class_probabilities", ml.classification().path("class_probabilities"));
        classification.put(
                "model_id", ml.classification().path("model").path("model_id").asText());
        String description = incident.getDescription() == null
                ? "No incident description supplied." : incident.getDescription();
        return new RagDiagnosisRequest(
                "rag_diagnosis_v1", incident.getId().toString(), incident.getTitle(), description,
                incident.getAffectedServices().stream().sorted().toList(), anomaly, classification,
                request.signalSummary() == null ? List.of() : request.signalSummary());
    }

    private JsonNode combinedLineage(JsonNode ml, JsonNode rag) {
        ObjectNode result = objectMapper.createObjectNode();
        result.set("ml", ml);
        if (rag != null) {
            result.set("rag", rag);
        }
        return result;
    }

    private JsonNode timings(long started, JsonNode ml, JsonNode rag) {
        ObjectNode result = objectMapper.createObjectNode();
        if (ml != null) {
            result.set("ml", ml);
        }
        if (rag != null) {
            result.set("rag", rag);
        }
        result.put("overall_ms", (System.nanoTime() - started) / 1_000_000.0);
        return result;
    }

    private String fingerprint(UUID incidentId, IntelligenceRunRequest request) {
        try {
            ObjectNode canonical = objectMapper.createObjectNode();
            canonical.put("incident_id", incidentId.toString());
            canonical.set("request", objectMapper.valueToTree(request));
            byte[] bytes = objectMapper.writer().writeValueAsBytes(canonical);
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (JsonProcessingException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("cannot calculate intelligence request fingerprint", exception);
        }
    }

    private static void validateRequest(IntelligenceRunRequest request) {
        if (request.featureSchemaVersion() != 1) {
            throw new IllegalArgumentException("feature_schema_version must be 1");
        }
        if (!request.featureNames().equals(FrozenFeatureContract.FEATURE_NAMES)
                || request.windows().stream().anyMatch(
                    window -> window.values().size() != FrozenFeatureContract.FEATURE_NAMES.size())) {
            throw new IllegalArgumentException(
                    "feature_names must exactly match the frozen Phase 5 ordering");
        }
    }

    private void assertIncident(UUID incidentId) {
        if (!incidentRepository.existsById(incidentId)) {
            throw new IncidentNotFoundException(incidentId);
        }
    }

    private IntelligenceRunResponse toResponse(IntelligenceRunEntity entity) {
        return new IntelligenceRunResponse(
                entity.getId(), entity.getIncidentId(), entity.getSchemaVersion(), entity.getInputId(),
                entity.getRequestHash(), entity.getStatus(), entity.isRequiresHumanReview(),
                entity.getCorrelationId(), entity.getMlResult(), entity.getIntelligenceResult(),
                entity.getLineage(), entity.getTimings(), entity.getFailureCode(),
                entity.getFailureMessage(), entity.getCreatedAt(), entity.getUpdatedAt(),
                entity.getCompletedAt(), entity.getVersion());
    }

    public record RunResult(IntelligenceRunResponse response, boolean created) {
    }
}
