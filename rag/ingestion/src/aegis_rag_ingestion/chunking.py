from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from aegis_rag_ingestion.contracts import ChunkDraft, SourceDocument, Tokenizer

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Section:
    heading_path: tuple[str, ...]
    text: str


def split_sections(body: str) -> tuple[Section, ...]:
    headings: list[str] = []
    lines: list[str] = []
    sections: list[Section] = []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            sections.append(Section(tuple(headings), text))

    for line in body.splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            lines.clear()
            level = len(match.group(1))
            del headings[level - 1 :]
            headings.append(match.group(2).strip())
        else:
            lines.append(line)
    flush()
    return tuple(sections)


def chunk_document(
    document: SourceDocument,
    tokenizer: Tokenizer,
    *,
    target_tokens: int,
    overlap_tokens: int,
    minimum_tokens: int = 8,
    schema_version: int = 1,
) -> tuple[ChunkDraft, ...]:
    chunks: list[ChunkDraft] = []
    for section in split_sections(document.body):
        token_ids = tokenizer.encode(section.text)
        if len(token_ids) < minimum_tokens:
            continue
        start = 0
        while start < len(token_ids):
            window = token_ids[start : start + target_tokens]
            content = tokenizer.decode(window).strip()
            if content:
                index = len(chunks)
                heading = " > ".join(section.heading_path)
                embedded_text = f"{document.metadata.title}\n{heading}\n{content}".strip()
                identity = "\0".join(
                    (
                        document.document_id,
                        document.checksum,
                        str(schema_version),
                        str(index),
                        heading,
                        content,
                    )
                )
                chunks.append(
                    ChunkDraft(
                        chunk_id=hashlib.sha256(identity.encode()).hexdigest(),
                        document_id=document.document_id,
                        index=index,
                        heading_path=section.heading_path,
                        content=content,
                        embedded_text=embedded_text,
                        token_count=len(window),
                    )
                )
            if start + target_tokens >= len(token_ids):
                break
            start += target_tokens - overlap_tokens
    return tuple(chunks)


def chunk_corpus(
    documents: tuple[SourceDocument, ...],
    tokenizer: Tokenizer,
    *,
    target_tokens: int,
    overlap_tokens: int,
    minimum_tokens: int = 8,
    schema_version: int = 1,
) -> tuple[ChunkDraft, ...]:
    return tuple(
        chunk
        for document in documents
        for chunk in chunk_document(
            document,
            tokenizer,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            minimum_tokens=minimum_tokens,
            schema_version=schema_version,
        )
    )
