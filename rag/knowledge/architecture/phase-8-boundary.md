---
title: Phase 8 Knowledge Ingestion Boundary
document_type: architecture
version: 1
services: [rag-service, postgresql, platform]
incident_types: [general]
synthetic: false
---
# Phase 8 Knowledge Ingestion Boundary

## Ownership

The isolated Python ingestion package owns corpus validation, deterministic chunking, embeddings, and the PostgreSQL `rag` schema. Spring Flyway continues to own incident-service tables. The health-only RAG FastAPI service does not import ingestion dependencies.

## Data contract

Documents have stable path-derived identities, semantic checksums, controlled metadata, and an active state. Chunks preserve heading context, token counts, embedded text, and normalized 384-dimensional vectors. Ingestion runs record configuration, counts, quality, and failures.

## Atomicity

A changed document and all replacement chunks commit together. Unchanged documents are skipped. Missing source documents become inactive rather than being deleted.

## Explicit exclusions

Phase 8 does not implement retrieval, ranking, BM25, reciprocal-rank fusion, question answering, generated recommendations, an SLM, or an LLM. One exact distance query exists only to validate vector storage.
