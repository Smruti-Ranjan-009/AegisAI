# AegisAI RAG reranking

This Python 3.12 package reranks the first ten Phase 9 Hybrid RRF candidates
with the pinned `cross-encoder/ms-marco-MiniLM-L6-v2` CPU model and exposes the
first five results as generation evidence. It preserves BM25, dense, and RRF
lineage and adds cross-encoder score/rank without changing Phase 9 retrieval.

Hosted tests use `FakeRerankerProvider`; real model weights are optional and
stored under ignored runtime cache. See `docs/reranking-and-grounded-generation.md`
for model setup, benchmark discipline, and CLI commands.
