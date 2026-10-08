from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DOCUMENT_TYPES = frozenset(
    {"runbook", "postmortem", "troubleshooting", "architecture", "procedure"}
)
INCIDENT_TYPES = frozenset(
    {
        "cpu_saturation",
        "memory_leak",
        "service_failure",
        "dependency_failure",
        "high_latency",
        "general",
    }
)
SERVICES = frozenset(
    {
        "incident-service",
        "telemetry-service",
        "ml-service",
        "rag-service",
        "postgresql",
        "kafka",
        "platform",
        "general",
        "ad",
        "email",
        "payment",
        "checkout",
        "frontend",
        "image-provider",
    }
)


@dataclass(frozen=True)
class DocumentMetadata:
    title: str
    document_type: str
    version: int
    services: tuple[str, ...]
    incident_types: tuple[str, ...]
    synthetic: bool


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    source_path: str
    checksum: str
    metadata: DocumentMetadata
    body: str


@dataclass(frozen=True)
class ChunkDraft:
    chunk_id: str
    document_id: str
    index: int
    heading_path: tuple[str, ...]
    content: str
    embedded_text: str
    token_count: int


@dataclass(frozen=True)
class EmbeddedChunk:
    draft: ChunkDraft
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class CorpusInspection:
    root: Path
    documents: tuple[SourceDocument, ...]
    chunks: tuple[ChunkDraft, ...]


class Tokenizer(Protocol):
    @property
    def identity(self) -> str: ...

    def encode(self, text: str) -> list[int]: ...

    def decode(self, token_ids: list[int]) -> str: ...


class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def normalized(self) -> bool: ...

    @property
    def tokenizer(self) -> Tokenizer: ...

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...
