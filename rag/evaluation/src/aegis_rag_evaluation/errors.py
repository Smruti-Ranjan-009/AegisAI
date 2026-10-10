class EvaluationError(Exception):
    """Base exception for explicit Phase 11 failures."""


class BenchmarkValidationError(EvaluationError):
    """The committed benchmark or gold contract is invalid."""


class ArtifactGuardError(EvaluationError):
    """A frozen artifact identity or write-once guard failed."""


class EvaluatorUnavailableError(EvaluationError):
    """The configured evaluator cannot be loaded or used."""
