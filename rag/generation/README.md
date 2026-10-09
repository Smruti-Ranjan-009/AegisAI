# AegisAI grounded generation

This Python 3.12 package turns five reranked evidence records into a compact,
machine-validated advisory diagnosis using an on-demand local llama.cpp server
and the pinned Qwen3 4B Q4_K_M GGUF. It rejects non-loopback endpoints,
malformed output, and invalid citations. Hosted CI uses a fake provider and
never downloads or starts the real model.

See `docs/reranking-and-grounded-generation.md` for the deliberate model setup,
Windows llama.cpp command, security contract, and local validation workflow.
