from pathlib import Path

import pytest

from aegis_rag_ingestion.errors import DocumentValidationError
from aegis_rag_ingestion.parsing import discover_documents, normalize_text, parse_document

VALID = """---
title: Example Runbook
document_type: runbook
version: 1
services: [platform]
incident_types: [general]
synthetic: true
---
# Response

Check the service health and preserve evidence.
"""


def test_normalize_text_removes_platform_and_trailing_whitespace() -> None:
    assert normalize_text("first  \r\nsecond\t\r") == "first\nsecond\n"


def test_parse_document_has_stable_path_identity(tmp_path: Path) -> None:
    first = tmp_path / "a" / "guide.md"
    first.parent.mkdir()
    first.write_text(VALID, encoding="utf-8")

    document = parse_document(first, tmp_path)

    assert document.source_path == "a/guide.md"
    assert len(document.document_id) == 64
    assert len(document.checksum) == 64
    assert document.metadata.services == ("platform",)


def test_crlf_does_not_change_checksum(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text(VALID, encoding="utf-8")
    first = parse_document(path, tmp_path)
    path.write_bytes(VALID.replace("\n", "\r\n").encode())
    second = parse_document(path, tmp_path)
    assert first == second


def test_metadata_change_updates_checksum_but_not_document_id(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text(VALID, encoding="utf-8")
    first = parse_document(path, tmp_path)
    path.write_text(VALID.replace("version: 1", "version: 2"), encoding="utf-8")
    second = parse_document(path, tmp_path)
    assert first.document_id == second.document_id
    assert first.checksum != second.checksum


def test_discovery_ignores_hidden_runtime_raw_and_binary_paths(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text(VALID, encoding="utf-8")
    for relative in (".hidden.md", ".runtime/output.md", "data/raw/capture.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(VALID, encoding="utf-8")
    (tmp_path / "weights.bin").write_bytes(b"not knowledge")

    documents = discover_documents(tmp_path)

    assert [document.source_path for document in documents] == ["guide.md"]


@pytest.mark.parametrize(
    "replacement, message",
    [
        ("document_type: unknown", "unsupported document_type"),
        ("services: [unknown]", "unsupported services"),
        ("synthetic: perhaps", "synthetic must be a boolean"),
    ],
)
def test_invalid_controlled_metadata_is_rejected(
    tmp_path: Path, replacement: str, message: str
) -> None:
    path = tmp_path / "guide.md"
    if replacement.startswith("document_type"):
        value = VALID.replace("document_type: runbook", replacement)
    elif replacement.startswith("services"):
        value = VALID.replace("services: [platform]", replacement)
    else:
        value = VALID.replace("synthetic: true", replacement)
    path.write_text(value, encoding="utf-8")
    with pytest.raises(DocumentValidationError, match=message):
        parse_document(path, tmp_path)
