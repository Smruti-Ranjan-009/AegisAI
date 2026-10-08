# AegisAI RAG ingestion

Phase 8 owns deterministic knowledge-document ingestion and the PostgreSQL
`rag` schema. It does not provide retrieval, ranking, question answering, or
generation.

From the repository root:

```powershell
python -m pip install -e ".\rag\ingestion[test,embeddings]"
python -m aegis_rag_ingestion inspect --json
python -m aegis_rag_ingestion migrate
python -m aegis_rag_ingestion ingest
python -m aegis_rag_ingestion validate --smoke-query "high CPU saturation"
```

The real embedding extra downloads `BAAI/bge-small-en-v1.5` on first use. Tests
and CI inject deterministic fake embeddings and require no model download.
Successful runs write an ignored manifest and quality report below
`.runtime/rag/ingestion`.
