# Phase 11 End-to-End Benchmark

`e2e-rag-v1-b61d8c044a77` is a new evaluator-only benchmark for the frozen
Phase 10 pipeline. It does not reuse Phase 9 or Phase 10 final queries.

The 40 committed cases contain 30 grounded, five insufficient-evidence, and
five adversarial cases. The explicit 25/15 development/final split is frozen in
`e2e_queries_v1.jsonl`. Grounded cases contain six examples for each of five
incident families and six examples for each of five query styles. The ten final
grounded cases contain two of every family and style.

`e2e_gold_v1.jsonl` was curated by reading the controlled corpus. Relevant
sections use the stable source-path plus full heading-path identity; grade 2 is
direct evidence and grade 1 is useful support. Required facts and acceptable
actions are concise propositions grounded in those documents. They are never
used by retrieval, reranking, prompting, or generation.

`adversarial_overlays_v1.jsonl` is evaluation-only. Each overlay is appended to
one retrieved evidence record after database retrieval and remains inside the
Phase 10 untrusted-evidence delimiters. The fake sentinel is not a secret, and
overlays must never be ingested into `rag.documents`.

The benchmark manifest binds queries, gold, overlays, the 65-chunk corpus, the
canonical Phase 10 pipeline, the independent NLI evaluator, and transparent
metric definitions. Development outputs may be regenerated to repair harness
bugs. Final canonical and final no-reranker outputs require explicit
confirmation and are write-once.
