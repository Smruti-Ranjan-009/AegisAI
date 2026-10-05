from __future__ import annotations


class PipelineError(Exception):
    """Base class for stable pipeline failures."""


class PermanentMessageError(PipelineError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


class TransientPipelineError(PipelineError):
    """A bounded retry may succeed without changing the source record."""


PERMANENT_CATEGORIES = frozenset(
    {
        "missing_header",
        "unsupported_signal",
        "invalid_utf8",
        "invalid_json",
        "invalid_otlp_structure",
        "processed_schema_validation",
    }
)


def is_permanent_category(category: str) -> bool:
    return category in PERMANENT_CATEGORIES
