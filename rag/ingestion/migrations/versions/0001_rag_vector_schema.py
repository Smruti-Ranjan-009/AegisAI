"""Create the Phase 8 RAG vector knowledge schema.

Revision ID: 0001_rag_vector_schema
Revises:
Create Date: 2026-10-08
"""

from alembic import op

revision = "0001_rag_vector_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE rag.documents (
            id text PRIMARY KEY,
            source_path text NOT NULL UNIQUE,
            title text NOT NULL,
            document_type text NOT NULL CHECK (
                document_type IN ('runbook', 'postmortem', 'troubleshooting',
                                  'architecture', 'procedure')
            ),
            version integer NOT NULL CHECK (version >= 1),
            checksum char(64) NOT NULL,
            synthetic boolean NOT NULL,
            services text[] NOT NULL,
            incident_types text[] NOT NULL,
            metadata jsonb NOT NULL,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rag.chunks (
            id text PRIMARY KEY,
            document_id text NOT NULL REFERENCES rag.documents(id) ON DELETE CASCADE,
            chunk_index integer NOT NULL CHECK (chunk_index >= 0),
            heading_path text[] NOT NULL,
            content text NOT NULL,
            embedded_text text NOT NULL,
            token_count integer NOT NULL CHECK (token_count > 0),
            embedding vector(384) NOT NULL,
            metadata jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rag.ingestion_runs (
            id text PRIMARY KEY,
            status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            started_at timestamptz NOT NULL,
            completed_at timestamptz,
            model_id text NOT NULL,
            embedding_dimension integer NOT NULL,
            embeddings_normalized boolean NOT NULL,
            chunk_config jsonb NOT NULL,
            counts jsonb,
            quality jsonb,
            errors jsonb,
            manifest jsonb NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_rag_documents_type ON rag.documents(document_type)")
    op.execute("CREATE INDEX idx_rag_documents_active ON rag.documents(active)")
    op.execute("CREATE INDEX idx_rag_documents_services ON rag.documents USING gin(services)")
    op.execute(
        "CREATE INDEX idx_rag_documents_incident_types ON rag.documents USING gin(incident_types)"
    )
    op.execute("CREATE INDEX idx_rag_chunks_document ON rag.chunks(document_id)")
    op.execute("CREATE INDEX idx_rag_runs_started ON rag.ingestion_runs(started_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE rag.chunks")
    op.execute("DROP TABLE rag.documents")
    op.execute("DROP TABLE rag.ingestion_runs")
