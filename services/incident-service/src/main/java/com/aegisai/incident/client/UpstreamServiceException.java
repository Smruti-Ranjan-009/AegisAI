package com.aegisai.incident.client;

public class UpstreamServiceException extends RuntimeException {
    private final String code;
    private final boolean validationFailure;

    public UpstreamServiceException(String code, String message, boolean validationFailure, Throwable cause) {
        super(message, cause);
        this.code = code;
        this.validationFailure = validationFailure;
    }

    public String getCode() { return code; }
    public boolean isValidationFailure() { return validationFailure; }
}

