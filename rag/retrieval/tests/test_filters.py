import pytest
from helpers import chunk

from aegis_rag_retrieval.contracts import SearchFilters
from aegis_rag_retrieval.errors import ConfigurationError


def test_filter_or_within_dimension_and_across_dimensions() -> None:
    filters = SearchFilters.validated(
        services=["checkout", "payment"],
        incident_types=["dependency_failure"],
        document_types=["runbook", "postmortem"],
    )
    assert filters.matches(
        chunk(
            "a",
            "text",
            services=("payment",),
            incident_types=("dependency_failure",),
            document_type="runbook",
        )
    )
    assert not filters.matches(
        chunk(
            "b",
            "text",
            services=("payment",),
            incident_types=("service_failure",),
        )
    )


def test_filter_rejects_unknown_controlled_values() -> None:
    with pytest.raises(ConfigurationError, match="unsupported services"):
        SearchFilters.validated(services=["x' OR true --"])

