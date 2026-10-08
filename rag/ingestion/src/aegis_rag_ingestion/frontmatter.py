from __future__ import annotations

from typing import Any

import yaml

from aegis_rag_ingestion.contracts import (
    DOCUMENT_TYPES,
    INCIDENT_TYPES,
    SERVICES,
    DocumentMetadata,
)
from aegis_rag_ingestion.errors import DocumentValidationError


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise DocumentValidationError("document must start with YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise DocumentValidationError("front matter is missing its closing delimiter")
    try:
        raw = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise DocumentValidationError(f"invalid YAML front matter: {exc}") from exc
    if not isinstance(raw, dict):
        raise DocumentValidationError("front matter must be a mapping")
    return raw, text[end + 5 :].strip() + "\n"


def validate_metadata(raw: dict[str, Any]) -> DocumentMetadata:
    required = {"title", "document_type", "version", "services", "incident_types", "synthetic"}
    missing = sorted(required - raw.keys())
    unknown = sorted(raw.keys() - required)
    if missing:
        raise DocumentValidationError(f"missing metadata fields: {', '.join(missing)}")
    if unknown:
        raise DocumentValidationError(f"unknown metadata fields: {', '.join(unknown)}")
    title = raw["title"]
    document_type = raw["document_type"]
    version = raw["version"]
    synthetic = raw["synthetic"]
    if not isinstance(title, str) or not title.strip():
        raise DocumentValidationError("title must be a non-empty string")
    if document_type not in DOCUMENT_TYPES:
        raise DocumentValidationError(f"unsupported document_type: {document_type!r}")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise DocumentValidationError("version must be an integer of at least 1")
    if not isinstance(synthetic, bool):
        raise DocumentValidationError("synthetic must be a boolean")
    services = _controlled_list("services", raw["services"], SERVICES)
    incidents = _controlled_list("incident_types", raw["incident_types"], INCIDENT_TYPES)
    return DocumentMetadata(
        title=title.strip(),
        document_type=document_type,
        version=version,
        services=services,
        incident_types=incidents,
        synthetic=synthetic,
    )


def _controlled_list(name: str, value: Any, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DocumentValidationError(f"{name} must be a non-empty list")
    if any(not isinstance(item, str) for item in value):
        raise DocumentValidationError(f"{name} entries must be strings")
    entries = tuple(dict.fromkeys(value))
    unsupported = sorted(set(entries) - allowed)
    if unsupported:
        raise DocumentValidationError(f"unsupported {name}: {', '.join(unsupported)}")
    return entries
