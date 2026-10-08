class IngestionError(Exception):
    """Base error for expected ingestion failures."""


class ConfigurationError(IngestionError):
    """Configuration is invalid or incomplete."""


class DocumentValidationError(IngestionError):
    """A source document violates the corpus contract."""


class EmbeddingValidationError(IngestionError):
    """An embedding violates the configured vector contract."""
