from aegis_rag_ingestion.chunking import chunk_document, split_sections
from aegis_rag_ingestion.contracts import DocumentMetadata, SourceDocument
from aegis_rag_ingestion.tokenization import DeterministicTokenizer


def document(body: str) -> SourceDocument:
    return SourceDocument(
        document_id="document-id",
        source_path="guide.md",
        checksum="checksum",
        metadata=DocumentMetadata(
            title="Guide",
            document_type="runbook",
            version=1,
            services=("platform",),
            incident_types=("general",),
            synthetic=True,
        ),
        body=body,
    )


def test_split_sections_preserves_heading_hierarchy() -> None:
    sections = split_sections("# One\nintro\n## Two\ndetail\n# Three\nend\n")
    assert [section.heading_path for section in sections] == [
        ("One",),
        ("One", "Two"),
        ("Three",),
    ]


def test_chunking_applies_token_window_and_overlap() -> None:
    tokenizer = DeterministicTokenizer()
    chunks = chunk_document(
        document("# Long\n" + " ".join(f"word{i}" for i in range(12))),
        tokenizer,
        target_tokens=5,
        overlap_tokens=2,
        minimum_tokens=1,
    )
    assert [chunk.token_count for chunk in chunks] == [5, 5, 5, 3]
    first = tokenizer.encode(chunks[0].content)
    second = tokenizer.encode(chunks[1].content)
    assert first[-2:] == second[:2]
    assert all(chunk.heading_path == ("Long",) for chunk in chunks)


def test_chunk_ids_are_repeatable_and_change_with_schema() -> None:
    tokenizer = DeterministicTokenizer()
    source = document("# Heading\ncontent for a repeatable chunk")
    first = chunk_document(
        source, tokenizer, target_tokens=20, overlap_tokens=2, minimum_tokens=1
    )
    second = chunk_document(
        source, tokenizer, target_tokens=20, overlap_tokens=2, minimum_tokens=1
    )
    changed = chunk_document(
        source,
        tokenizer,
        target_tokens=20,
        overlap_tokens=2,
        minimum_tokens=1,
        schema_version=2,
    )
    assert first == second
    assert first[0].chunk_id != changed[0].chunk_id
    assert first[0].embedded_text.startswith("Guide\nHeading\n")


def test_tiny_content_only_section_is_not_emitted() -> None:
    chunks = chunk_document(
        document("# Heading\none word"),
        DeterministicTokenizer(),
        target_tokens=20,
        overlap_tokens=2,
        minimum_tokens=3,
    )
    assert chunks == ()
