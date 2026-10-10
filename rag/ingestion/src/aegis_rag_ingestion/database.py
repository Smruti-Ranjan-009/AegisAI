from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg
from pgvector.psycopg import register_vector


def psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def require_isolated_test_database(database_url: str) -> str:
    """Reject destructive test setup unless the database is explicitly test-scoped."""
    database = urlparse(psycopg_url(database_url)).path.lstrip("/").casefold()
    if not database or "test" not in database or database == "aegisai":
        raise ValueError(
            "destructive RAG tests require a database name containing 'test'; "
            f"refusing {database or '<missing>'}"
        )
    return database_url


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(psycopg_url(database_url)) as connection:
        register_vector(connection)
        yield connection
