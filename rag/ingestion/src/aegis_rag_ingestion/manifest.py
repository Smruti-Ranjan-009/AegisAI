from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis_rag_ingestion.config import IngestionConfig
from aegis_rag_ingestion.contracts import EmbeddingProvider, SourceDocument


def build_manifest(
    run_id: str,
    config: IngestionConfig,
    provider: EmbeddingProvider,
    documents: tuple[SourceDocument, ...],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "ingestion_run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "started_at_utc": datetime.now(UTC).isoformat(),
        "corpus_root": config.corpus_root.relative_to(config.repository).as_posix(),
        "sources": [
            {
                "document_id": document.document_id,
                "source_path": document.source_path,
                "checksum": document.checksum,
                "version": document.metadata.version,
            }
            for document in documents
        ],
        "embedding": {
            "model_id": provider.model_id,
            "model_revision": provider.model_revision,
            "dimension": provider.dimension,
            "normalized": provider.normalized,
            "device": config.device,
            "tokenizer": provider.tokenizer.identity,
        },
        "chunking": {
            "schema_version": config.chunk_schema_version,
            "strategy": "markdown-heading-token-window",
            "target_tokens": config.target_tokens,
            "overlap_tokens": config.overlap_tokens,
            "minimum_chunk_tokens": config.minimum_chunk_tokens,
        },
    }


def write_run_outputs(
    runtime_root: Path,
    run_id: str,
    manifest: dict[str, Any],
    quality: dict[str, Any],
) -> Path:
    run_directory = runtime_root / "ingestion" / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    _write_json(run_directory / "manifest.json", manifest)
    _write_json(run_directory / "quality.json", quality)
    return run_directory


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
