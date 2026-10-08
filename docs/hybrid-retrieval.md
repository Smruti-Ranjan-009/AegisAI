# Phase 9 hybrid retrieval

Phase 9 adds offline retrieval evaluation over the Phase 8 knowledge store. It
does not add an HTTP endpoint, reranker, cross-encoder, SLM, LLM, answer
generation, or prompt orchestration. `services/rag-service` remains health-only.

## Retrieval package and snapshot

`rag/retrieval` is an independently installable Python 3.12 project. The local
Phase 8 ingestion package is installed alongside it so retrieval can reuse the
frozen BGE provider, vector validation, PostgreSQL connection setup, and
controlled metadata vocabularies.

At startup, retrieval loads only chunks whose owning document is active. It
hashes sorted active document IDs/checksums and chunk IDs into one corpus
fingerprint. BM25 is built from that snapshot, dense SQL includes `d.active`,
and benchmark execution verifies that the fingerprint did not change before
the report is accepted.

Validated Phase 9 snapshot:

- 15 active documents and 65 active chunks
- fingerprint `f5a7d43a5ca429013ef4117b52a36ca68e4e4b4f4e1d16a6d13e89867f59443b`
- benchmark `retrieval-v1-d0069399f493`

## BM25

The lexical branch uses `rank-bm25` 0.2.2 `BM25Okapi` with fixed `k1=1.5` and
`b=0.75`. Its in-memory document text is `title + heading path + content`.
The deterministic case-folded tokenizer preserves operational terms such as
`5xx`, `OOM`, `p95`, `PostgreSQL`, `connection_pool`, and `image-provider`, and
also emits component tokens for hyphen/underscore/dot compounds. Index build
time is recorded separately from query latency.

## Dense retrieval

The dense branch reuses `BAAI/bge-small-en-v1.5` at commit
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, the Phase 8 query instruction,
normalized 384-dimensional vectors, and CPU execution. PostgreSQL calculates
exact cosine distance with `<=>`; there is no HNSW or IVFFlat index because 65
chunks do not justify approximate retrieval.

## Filters

The common filter contract accepts controlled `services`, `incident_types`, and
`document_types`. Values are ORed within a dimension and ANDed across
dimensions. BM25 applies the contract to its snapshot objects. Dense retrieval
uses bound psycopg parameters with array-overlap/`ANY` operators; values are
never interpolated into SQL. The primary benchmark is always unfiltered. Six
separate filter-assisted checks achieved a 1.000 hit rate.

## Reciprocal rank fusion

Each branch contributes at most 20 candidates. Equal-weight RRF uses
`1 / (60 + rank)` per present branch. Results sort by descending fused score,
then best branch rank, then stable chunk ID. Raw BM25 and cosine similarity
remain available for diagnostics but are never directly added together.

## Benchmark governance

The committed v1 assets contain 50 primary queries and 100 manually curated,
section-level qrels. The 30-query development and 20-query final split is fixed
and balanced as described in `rag/evaluation/README.md`. Inputs are frozen by
SHA-256 before the final split. Reports are written as JSON and Markdown below
ignored `.runtime/rag/retrieval/<benchmark-id>/`.

Development NDCG@10 was 0.711 for BM25, 0.751 for dense, and 0.815 for hybrid.
Hybrid development Recall@5 was 0.800, MRR@10 was 0.881, and Hit@10 was 1.000.
At rank 1, BM25 alone hit five queries and dense alone hit nine, demonstrating
branch complementarity; both hit 12 and neither hit four.

The frozen final split was executed once. No qrel, query, corpus, or retrieval
configuration was changed afterward.

| Method | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | NDCG@5 | NDCG@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.275 | 0.525 | 0.600 | 0.850 | 0.714 | 0.571 | 0.670 |
| Dense | 0.350 | 0.600 | 0.750 | 0.775 | 0.798 | 0.727 | 0.732 |
| Hybrid | 0.325 | 0.575 | 0.750 | 0.850 | 0.785 | 0.700 | **0.733** |

Hybrid final Hit@1/3/5/10 was 0.650/0.900/0.950/1.000. Hybrid NDCG@10
by incident family ranged from 0.603 for CPU saturation to 0.861 for high
latency; by style it ranged from 0.552 for symptoms to 0.873 for operational
questions. At rank 1, BM25 alone hit three queries, dense alone hit six, both
hit eight, and neither hit three. Hybrid narrowly led the primary NDCG@10
metric, while dense alone had the best Recall@1, Recall@3, MRR@10, and NDCG@5;
the fusion result is therefore useful but not a universal branch improvement.

Final warmed CPU latency excluded model load. BM25 p50/p95/p99 was
0.344/0.480/0.499 ms; dense embedding plus SQL was 16.656/17.486/19.659 ms;
hybrid total was 17.139/18.117/20.321 ms. Mean query embedding, exact SQL, and
RRF time was 14.827, 1.874, and 0.156 ms respectively. BM25 index construction
took 2.538 ms.

## Corpus metadata audit

All 15 documents were reviewed against their actual content and the Phase 1
fault catalog. The controlled service vocabulary gained `ad`, `email`,
`payment`, `checkout`, `frontend`, and `image-provider`. Only the five matching
incident-family runbooks were updated. No document body was changed.

| Source | Old checksum prefix | New checksum prefix | Replaced chunks |
|---|---|---|---:|
| `runbooks/cpu-saturation.md` | `43f927c13ffa` | `db1b3dc52af9` | 4 |
| `runbooks/memory-leak.md` | `3059312a873d` | `7cf07ab26334` | 4 |
| `runbooks/service-failure.md` | `c2f4ebfbcdb7` | `04cb07dd2a60` | 4 |
| `runbooks/dependency-failure.md` | `f9c16525e19e` | `c38f1a99a123` | 4 |
| `runbooks/high-latency.md` | `e4595ca62724` | `0df784a36c93` | 4 |

The real re-ingestion updated five documents, removed and replaced 20 stable
checksum-derived chunk IDs, retained 65 total chunks, and reported no empty,
duplicate, non-finite, or dimension-invalid chunks.

## Security and limitations

- Database credentials come from environment configuration; no secret appears
  in benchmark output or source control.
- Controlled filters and bound SQL parameters reject arbitrary metadata values.
- Retrieved content is untrusted data. A future generation phase must treat it
  as evidence, not executable instructions.
- The corpus is small and mostly synthetic, qrels were reviewed by one author,
  and latency was measured on one development CPU. Results are portfolio
  evidence, not production SLOs.
- Exact dense search and in-memory BM25 are appropriate for 65 chunks; scaling
  decisions require a larger representative corpus and new measurements.

## Validation commands

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[embeddings]"
python -m pip install -e ".\rag\retrieval[test]"
docker compose up -d --wait postgres
python -m aegis_rag_retrieval validate-benchmark --json
python -m pytest rag\retrieval\tests -q --basetemp=.runtime\pytest-phase9
python -m ruff check rag\retrieval
python -m aegis_rag_retrieval search "database connection exhaustion" --method hybrid --top-k 5 --json
python -m aegis_rag_retrieval filter-evaluate --json
docker compose down --remove-orphans
```
