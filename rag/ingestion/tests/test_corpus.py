from pathlib import Path

from aegis_rag_ingestion.parsing import discover_documents


def test_repository_corpus_has_required_coverage() -> None:
    root = Path(__file__).resolve().parents[3] / "rag" / "knowledge"
    documents = discover_documents(root)
    assert len(documents) == 15
    assert {document.metadata.document_type for document in documents} == {
        "runbook",
        "postmortem",
        "troubleshooting",
        "architecture",
        "procedure",
    }
    incident_types = {
        item for document in documents for item in document.metadata.incident_types
    }
    assert {
        "cpu_saturation",
        "memory_leak",
        "service_failure",
        "dependency_failure",
        "high_latency",
    } <= incident_types
    assert sum(document.metadata.synthetic for document in documents) == 13
