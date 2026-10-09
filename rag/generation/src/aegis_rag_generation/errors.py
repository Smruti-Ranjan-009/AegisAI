class GenerationError(Exception):
    """Base error for safe generation handling."""


class GenerationConfigurationError(GenerationError):
    """Raised for unsafe or invalid local generation configuration."""


class ModelIntegrityError(GenerationError):
    """Raised when the local GGUF does not match the pinned bytes."""


class SLMUnavailableError(GenerationError):
    """Raised when the configured local SLM cannot serve the request."""


class ContextBudgetError(GenerationError):
    """Raised when the irreducible prompt cannot fit the context."""


class GenerationValidationError(GenerationError):
    """Raised when generated JSON, schema, or citations fail closed."""
