from contextlib import AbstractContextManager
from typing import Any

from aegis_rag_retrieval.contracts import SearchFilters
from aegis_rag_retrieval.repository import RetrievalRepository


class SpyCursor(AbstractContextManager):
    def __init__(self) -> None:
        self.statement = ""
        self.parameters: list[Any] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement: str, parameters: list[Any]) -> None:
        self.statement = statement
        self.parameters = parameters

    def fetchall(self) -> list[Any]:
        return []


class SpyConnection:
    def __init__(self) -> None:
        self.cursor_instance = SpyCursor()

    def cursor(self, **kwargs):
        del kwargs
        return self.cursor_instance


def test_dense_filters_are_bound_parameters_not_sql_text() -> None:
    connection = SpyConnection()
    repository = RetrievalRepository(connection)  # type: ignore[arg-type]
    repository.dense_search(
        (1.0, 0.0),
        limit=5,
        filters=SearchFilters.validated(
            services=["image-provider"],
            incident_types=["high_latency"],
            document_types=["runbook"],
        ),
    )
    cursor = connection.cursor_instance
    assert "image-provider" not in cursor.statement
    assert "high_latency" not in cursor.statement
    assert cursor.parameters[1:4] == [
        ["image-provider"],
        ["high_latency"],
        ["runbook"],
    ]
