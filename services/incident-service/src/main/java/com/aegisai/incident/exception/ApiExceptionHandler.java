package com.aegisai.incident.exception;

import jakarta.persistence.OptimisticLockException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import java.net.URI;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger LOGGER = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(IncidentNotFoundException.class)
    ProblemDetail handleNotFound(IncidentNotFoundException exception, HttpServletRequest request) {
        return problem(HttpStatus.NOT_FOUND, "incident_not_found", exception.getMessage(), request);
    }

    @ExceptionHandler(InvalidIncidentTransitionException.class)
    ProblemDetail handleInvalidTransition(
            InvalidIncidentTransitionException exception,
            HttpServletRequest request) {
        LOGGER.warn("Rejected incident lifecycle request: {}", exception.getMessage());
        return problem(HttpStatus.CONFLICT, "invalid_incident_transition", exception.getMessage(), request);
    }

    @ExceptionHandler({OptimisticLockingFailureException.class, OptimisticLockException.class})
    ProblemDetail handleOptimisticConflict(Exception exception, HttpServletRequest request) {
        LOGGER.warn("Optimistic locking conflict for path={}", request.getRequestURI());
        return problem(
                HttpStatus.CONFLICT,
                "optimistic_lock_conflict",
                "The incident was updated by another request. Reload it and retry.",
                request);
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ProblemDetail handleDataConflict(DataIntegrityViolationException exception, HttpServletRequest request) {
        return problem(
                HttpStatus.CONFLICT,
                "database_conflict",
                "The requested change conflicts with persisted data.",
                request);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleValidation(MethodArgumentNotValidException exception, HttpServletRequest request) {
        ProblemDetail detail = problem(
                HttpStatus.BAD_REQUEST,
                "validation_failed",
                "One or more request fields are invalid.",
                request);
        Map<String, String> fields = new LinkedHashMap<>();
        exception.getBindingResult().getFieldErrors().forEach(error ->
                fields.putIfAbsent(error.getField(), error.getDefaultMessage()));
        detail.setProperty("field_errors", fields);
        return detail;
    }

    @ExceptionHandler(ConstraintViolationException.class)
    ProblemDetail handleConstraintViolation(
            ConstraintViolationException exception,
            HttpServletRequest request) {
        ProblemDetail detail = problem(
                HttpStatus.BAD_REQUEST,
                "validation_failed",
                "One or more request parameters are invalid.",
                request);
        Map<String, String> fields = new LinkedHashMap<>();
        exception.getConstraintViolations().forEach(violation ->
                fields.put(violation.getPropertyPath().toString(), violation.getMessage()));
        detail.setProperty("field_errors", fields);
        return detail;
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    ProblemDetail handleMalformedRequest(Exception exception, HttpServletRequest request) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "validation_failed",
                "The request body or parameter value is invalid.",
                request);
    }

    private static ProblemDetail problem(
            HttpStatus status,
            String errorCode,
            String message,
            HttpServletRequest request) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(status, message);
        detail.setTitle(status.getReasonPhrase());
        detail.setType(URI.create("https://aegisai.local/problems/" + errorCode));
        detail.setInstance(URI.create(request.getRequestURI()));
        detail.setProperty("error_code", errorCode);
        detail.setProperty("timestamp", Instant.now());
        return detail;
    }
}
