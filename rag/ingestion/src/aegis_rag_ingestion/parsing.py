from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from aegis_rag_ingestion.contracts import SourceDocument
from aegis_rag_ingestion.errors import DocumentValidationError
from aegis_rag_ingestion.frontmatter import split_front_matter, validate_metadata

TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
EXCLUDED_DIRECTORIES = frozenset(
    {".git", ".runtime", "runtime", "__pycache__", "artifacts", "models", "model-cache"}
)


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = TRAILING_SPACE.sub("", normalized)
    return normalized.rstrip() + "\n"


def parse_document(path: Path, corpus_root: Path) -> SourceDocument:
    try:
        relative = path.resolve().relative_to(corpus_root.resolve()).as_posix()
    except ValueError as exc:
        raise DocumentValidationError(f"source is outside corpus root: {path}") from exc
    text = normalize_text(path.read_text(encoding="utf-8"))
    raw_metadata, body = split_front_matter(text)
    metadata = validate_metadata(raw_metadata)
    if not body.strip():
        raise DocumentValidationError("document body must not be empty")
    document_id = hashlib.sha256(relative.encode()).hexdigest()
    canonical = {
        "body": normalize_text(body),
        "document_type": metadata.document_type,
        "incident_types": metadata.incident_types,
        "services": metadata.services,
        "synthetic": metadata.synthetic,
        "title": metadata.title,
        "version": metadata.version,
    }
    checksum = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SourceDocument(
        document_id=document_id,
        source_path=relative,
        checksum=checksum,
        metadata=metadata,
        body=normalize_text(body),
    )


def discover_documents(corpus_root: Path) -> tuple[SourceDocument, ...]:
    if not corpus_root.is_dir():
        raise DocumentValidationError(f"corpus root does not exist: {corpus_root}")
    paths = sorted(path for path in corpus_root.rglob("*") if _is_supported_path(path, corpus_root))
    if not paths:
        raise DocumentValidationError(f"no Markdown or text documents found under {corpus_root}")
    documents = tuple(parse_document(path, corpus_root) for path in paths)
    source_paths = [document.source_path for document in documents]
    if len(source_paths) != len(set(source_paths)):
        raise DocumentValidationError("duplicate normalized source paths discovered")
    return documents


def _is_supported_path(path: Path, corpus_root: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
        return False
    relative_parts = path.relative_to(corpus_root).parts
    if any(part.startswith(".") or part in EXCLUDED_DIRECTORIES for part in relative_parts):
        return False
    return not (len(relative_parts) >= 2 and relative_parts[:2] == ("data", "raw"))
