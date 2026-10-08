# Phase 8 RAG Ingestion and Vector Knowledge Base

Phase 8 implements only the knowledge-ingestion and vector-storage foundation.
It does not implement retrieval, BM25, fusion, reranking, question answering,
generation, an SLM, or an LLM API.

## Corpus contract

The committed corpus under `rag/knowledge` contains 15 concise operational
documents: five runbooks, five explicitly synthetic postmortems, three
troubleshooting guides, one architecture note, and one operating procedure.
Every Markdown file begins with validated YAML metadata: `title`, controlled
`document_type`, integer `version`, controlled `services` and `incident_types`
lists, and boolean `synthetic`.

Paths are repository-relative and normalized to POSIX separators. Document IDs
are SHA-256 hashes of those stable paths. Checksums cover canonical metadata and
LF-normalized content, so CRLF conversion does not create a false update.

## Parsing and chunking

The parser strips front matter from embedded content and preserves Markdown
heading paths. The production chunker uses the selected embedding model's real
tokenizer, a 400-token maximum window, and 60-token overlap for long sections.
The title and heading path are prepended only to `embedded_text`; the clean chunk
body is retained separately. Content-only sections below eight tokens are not
emitted as low-value chunks.

Chunk IDs include the document ID and checksum, heading, position, content, and
chunk schema version. A meaningful source change therefore generates a new,
auditable chunk set. The dependency-light `inspect` command uses a simple local
tokenizer and labels its token count as an estimate; ingestion uses BGE's actual
tokenizer.

## Embedding contract

Real local ingestion uses `BAAI/bge-small-en-v1.5` on CPU:

- 384 dimensions and normalized document/query vectors
- 512-token model limit, with ingestion capped below it
- the BGE retrieval instruction applied to queries only
- model dependencies isolated behind the package's `embeddings` extra

The model is pinned to Hugging Face revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; manifests record both identity
and revision.

Tests and hosted CI inject `aegis-fake-embedding-v1`. It is deterministic and
normalized and uses 384 dimensions for database integration, but it is never a
production model and is not used for the committed validation corpus.

## Schema ownership

Alembic in `rag/ingestion` is the sole owner of the PostgreSQL `rag` schema.
Spring Flyway continues to own the incident tables. The initial migration creates
the `vector` extension and:

- `rag.documents`: stable source identity, checksum, controlled metadata, and active state
- `rag.chunks`: heading context, clean and embedded text, token count, and `vector(384)`
- `rag.ingestion_runs`: model/chunk configuration, counts, quality, manifest, and errors

The schema has relational, GIN, and operational indexes but intentionally no
HNSW or IVFFlat index. Exact scans are the simplest correct starting point for a
small Phase 8 corpus.

## Idempotency and failure behavior

Unchanged document checksums are skipped. A changed document and its complete
replacement chunk set commit atomically. Sources missing from a later complete
corpus scan are marked inactive rather than deleted. A source returning at the
same path retains its identity and is reactivated.

Embedding and parsing complete before any knowledge rows change. A database
failure rolls back every document change in that run. Run state records either
completion or the expected failure message. Generated manifests and quality
reports are written beneath ignored `.runtime/rag/ingestion` after a successful
commit. Each manifest records start/completion timestamps, source IDs and
checksums, model revision, chunk configuration, insert/update/remove counts,
schema and pgvector versions, and measured parse/chunk, embedding, database, and
overall durations without including the database URL or credentials.

## Local setup and commands

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[test,embeddings]"
docker compose up -d --wait postgres

python -m aegis_rag_ingestion inspect --json
python -m aegis_rag_ingestion migrate --json
python -m aegis_rag_ingestion embed-validate --json
python -m aegis_rag_ingestion ingest --json
python -m aegis_rag_ingestion ingest --json
python -m aegis_rag_ingestion validate --smoke-query "database connection exhaustion" --json
python -m aegis_rag_ingestion status --json
```

The second ingestion should report all 15 documents skipped and zero chunks
written. The smoke query is an exact pgvector distance check, not a retrieval
feature or API.

## Tests and CI

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[test]"
python -m pytest rag\ingestion\tests -q --basetemp=.runtime\pytest-phase8
python -m ruff check rag\ingestion
```

PostgreSQL integration tests run only when `AEGIS_RAG_TEST_DATABASE_URL` points
to an explicitly disposable test database. Hosted CI provisions the pinned
pgvector image and uses fake embeddings, so it does not depend on Hugging Face
availability or model downloads.

## Image and volume compatibility

Compose pins `pgvector/pgvector:0.8.6-pg18-bookworm` by OCI index digest. This is
PostgreSQL 18 with pgvector 0.8.6, preserving the project's existing PostgreSQL
major version and named `aegis-postgres-data` volume. Normal validation must use
`docker compose down` without `-v`; volume deletion is an explicit destructive
operation.

## Phase 8 limitations

The corpus is small, English-only, and intentionally synthetic where labeled.
Embedding relevance is not evaluated in this phase. There is no retrieval API,
hybrid search, ranking, grounding, generation, model serving, or automated
ingestion event. Those require separate measured phases.
