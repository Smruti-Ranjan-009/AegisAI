# Retrieval benchmark v1

The primary Phase 9 benchmark contains 50 hand-authored, paraphrased operational
queries and 100 manually curated graded qrels over actual corpus sections.
Relevant sections use stable `source_path` plus `heading_path` identities rather
than database-generated IDs. Grade 2 means directly relevant and grade 1 means
supporting context.

The set is balanced across five incident families and five query styles:
symptom, signal, root cause, mitigation, and operational question. It has a
fixed 30-query development split and a 20-query final split. Each incident
family contributes four final queries, and each style appears four times in the
final split. Primary queries contain query text only—no metadata filters.

Files:

- `retrieval_queries_v1.jsonl`: primary query text, family, style, and split.
- `retrieval_qrels_v1.jsonl`: manually reviewed section-level relevance.
- `retrieval_filter_cases_v1.jsonl`: six secondary filter-assisted checks kept
  separate from primary quality claims.

Primary reporting includes Recall and Hit Rate at 1/3/5/10, MRR@10, NDCG@5/10,
per-family and per-style breakdowns, lexical/dense complementarity, and warmed
CPU latency. NDCG@10 is the primary metric. Query, qrel, retrieval-configuration,
and active-corpus hashes create the deterministic benchmark ID. The final split
is not used for tuning and the CLI refuses to overwrite an existing final report.

