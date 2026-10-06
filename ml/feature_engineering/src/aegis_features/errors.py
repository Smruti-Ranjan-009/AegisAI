class FeatureEngineeringError(Exception):
    """Base class for safe, user-facing feature engineering failures."""


class InputValidationError(FeatureEngineeringError):
    """Raised when a capture or OTLP record violates its input contract."""


class DataQualityError(FeatureEngineeringError):
    """Raised when a dataset exceeds a configured quality gate."""


class DuplicateConflictError(DataQualityError):
    """Raised when one source event identity has conflicting content."""
