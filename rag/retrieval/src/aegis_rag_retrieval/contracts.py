from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aegis_rag_ingestion.contracts import DOCUMENT_TYPES, INCIDENT_TYPES, SERVICES

from aegis_rag_retrieval.errors import ConfigurationError


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    document_checksum: str
    source_path: str
    title: str
    document_type: str
    services: tuple[str, ...]
    incident_types: tuple[str, ...]
    heading_path: tuple[str, ...]
    content: str

    @property
    def lexical_text(self) -> str:
        return "\n".join((self.title, " > ".join(self.heading_path), self.content))


@dataclass(frozen=True)
class CorpusSnapshot:
    fingerprint: str
    chunks: tuple[ChunkRecord, ...]
    active_documents: int


@dataclass(frozen=True)
class SearchFilters:
    services: tuple[str, ...] = ()
    incident_types: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()

    @classmethod
    def validated(
        cls,
        *,
        services: tuple[str, ...] | list[str] = (),
        incident_types: tuple[str, ...] | list[str] = (),
        document_types: tuple[str, ...] | list[str] = (),
    ) -> SearchFilters:
        return cls(
            services=_validate_values("services", services, SERVICES),
            incident_types=_validate_values("incident_types", incident_types, INCIDENT_TYPES),
            document_types=_validate_values("document_types", document_types, DOCUMENT_TYPES),
        )

    @property
    def active(self) -> bool:
        return bool(self.services or self.incident_types or self.document_types)

    def matches(self, chunk: ChunkRecord) -> bool:
        return (
            (not self.services or bool(set(self.services) & set(chunk.services)))
            and (
                not self.incident_types
                or bool(set(self.incident_types) & set(chunk.incident_types))
            )
            and (not self.document_types or chunk.document_type in self.document_types)
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "services": list(self.services),
            "incident_types": list(self.incident_types),
            "document_types": list(self.document_types),
        }


def _validate_values(
    name: str,
    values: tuple[str, ...] | list[str],
    allowed: frozenset[str],
) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(values))
    invalid = sorted(set(normalized) - allowed)
    if invalid:
        raise ConfigurationError(f"unsupported {name}: {', '.join(invalid)}")
    return normalized


@dataclass(frozen=True)
class RankedChunk:
    chunk: ChunkRecord
    rank: int
    score: float


@dataclass(frozen=True)
class RetrievalHit:
    chunk: ChunkRecord
    rank: int
    score: float
    bm25_rank: int | None = None
    bm25_score: float | None = None
    dense_rank: int | None = None
    dense_score: float | None = None

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "rank": self.rank,
            "score": self.score,
            "chunk_id": self.chunk.chunk_id,
            "document_id": self.chunk.document_id,
            "source_path": self.chunk.source_path,
            "title": self.chunk.title,
            "document_type": self.chunk.document_type,
            "services": list(self.chunk.services),
            "incident_types": list(self.chunk.incident_types),
            "heading_path": list(self.chunk.heading_path),
            "bm25_rank": self.bm25_rank,
            "bm25_score": self.bm25_score,
            "dense_rank": self.dense_rank,
            "dense_score": self.dense_score,
        }
        if include_content:
            value["content"] = self.chunk.content
        return value
