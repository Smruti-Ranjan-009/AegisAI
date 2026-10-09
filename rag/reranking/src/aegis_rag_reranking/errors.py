class RerankingError(Exception):
    """Base error for safe CLI handling."""


class RerankerConfigurationError(RerankingError):
    """Raised when the frozen reranking contract is invalid."""


class RerankerProviderError(RerankingError):
    """Raised when a reranking provider cannot score candidates safely."""


class RerankingBenchmarkError(RerankingError):
    """Raised when benchmark inputs or freeze discipline are invalid."""
