# AegisAI Phase 9 retrieval package

This Python 3.12 package provides offline BM25, exact pgvector dense search,
and reciprocal-rank fusion over the active Phase 8 corpus. It is deliberately
separate from the health-only `services/rag-service` application.

Install the local ingestion dependency first, then this package:

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[embeddings]"
python -m pip install -e ".\rag\retrieval[test]"
```

With PostgreSQL running and the Phase 8 corpus ingested:

```powershell
python -m aegis_rag_retrieval search "PostgreSQL connection pool exhausted" --method hybrid --top-k 5 --json
python -m aegis_rag_retrieval search "slow image response" --service image-provider --incident-type high_latency --json
python -m aegis_rag_retrieval validate-benchmark --json
python -m aegis_rag_retrieval benchmark --split development --json
python -m aegis_rag_retrieval filter-evaluate --json
```

The final split is guarded and may be run only after a development run freezes
the corpus, query, qrel, and configuration hashes:

```powershell
python -m aegis_rag_retrieval benchmark --split test --confirm-final-test --json
```

Generated reports live under `.runtime/rag/retrieval/` and are intentionally
ignored. Search output omits chunk bodies unless `--include-content` is given.
See [hybrid-retrieval.md](../../docs/hybrid-retrieval.md) for contracts,
methodology, measured results, and limitations.

