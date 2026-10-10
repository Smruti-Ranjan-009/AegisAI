import pytest

from aegis_rag_ingestion.database import require_isolated_test_database


def test_destructive_test_database_guard_accepts_isolated_name() -> None:
    url = "postgresql://aegis:password@localhost:5432/aegis_rag_test"
    assert require_isolated_test_database(url) == url


@pytest.mark.parametrize("database", ["aegisai", "postgres", "", "aegis_rag"])
def test_destructive_test_database_guard_rejects_non_test_database(database: str) -> None:
    with pytest.raises(ValueError, match="destructive RAG tests require"):
        require_isolated_test_database(f"postgresql://aegis:password@localhost:5432/{database}")
