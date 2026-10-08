class RetrievalError(Exception):
    """Expected, safe-to-report retrieval failure."""


class ConfigurationError(RetrievalError):
    """Invalid retrieval configuration."""


class BenchmarkError(RetrievalError):
    """Invalid benchmark data or execution state."""

