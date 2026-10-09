# Phase 10 reranking benchmark

This benchmark is independent of the observed Phase 9 final split. It contains
30 newly authored incident-engineer queries and 60 manually inspected section
qrels. Relevance is defined by source path and heading path: grade 2 is directly
responsive and grade 1 is useful supporting evidence.

The split is frozen at 20 development and 10 final queries. Each of the five
incident families and five query styles has six queries overall and two in the
final split. Primary evaluation is NDCG@5 for Hybrid RRF versus Hybrid RRF plus
the pinned cross-encoder. The final report is guarded against overwrite.

Qrels were curated from corpus content, never from retrieval/reranker ranks or
metadata labels alone. Both files use UTF-8 JSONL with LF line endings.
