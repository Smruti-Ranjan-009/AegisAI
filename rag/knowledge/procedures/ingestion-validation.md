---
title: Knowledge Ingestion Validation Procedure
document_type: procedure
version: 1
services: [rag-service, postgresql]
incident_types: [general]
synthetic: false
---
# Knowledge Ingestion Validation Procedure

## Preconditions

Use Python 3.12 and install the isolated ingestion project. Start the pinned PostgreSQL pgvector container without deleting an existing named volume. Configure the database URL through the documented environment variable.

## Validate sources

Run the inspect command before loading the embedding model. Resolve invalid metadata, empty documents, unsupported controlled values, or duplicate paths. Review the document and chunk distribution.

## Migrate and ingest

Apply the Alembic upgrade, then run ingestion with the local CPU model. Preserve the generated manifest and quality report under the ignored runtime directory. Run ingestion a second time and confirm every document is skipped with no duplicate chunks.

## Verify storage

Run store validation and one exact vector smoke query. Confirm vector dimension and normalization, active document count, chunk ownership, extension version, and schema revision. Stop containers after validation; retain the named development volume unless intentional cleanup was approved.
