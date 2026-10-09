# Reranking and Local Grounded Generation

Phase 10 extends the offline Phase 9 retrieval path with a CPU cross-encoder and
an on-demand, local quantized SLM. It does not add an HTTP diagnosis endpoint,
change the health-only RAG service, or perform formal answer-quality evaluation.

## Implemented path

```text
query -> BM25 + dense retrieval -> fixed RRF -> top 10 candidates
      -> MiniLM cross-encoder -> top 5 evidence records [E1]...[E5]
      -> token-budgeted grounded_incident_v1 prompt
      -> loopback llama.cpp / Qwen3-4B-Q4_K_M
      -> strict Pydantic and citation validation
      -> grounded diagnosis or explicit insufficient_evidence
```

Every reranked result retains its BM25, dense, and RRF rank/score lineage and
adds a cross-encoder score and rank. A passage contains only title, heading path,
and content. Ties use the original RRF rank and then chunk ID.

## Frozen model contracts

The reranker is `cross-encoder/ms-marco-MiniLM-L6-v2`, revision
`233902d25c440f23af6f7d6e94d2946bac0bee0a`. Its required
`model.safetensors` SHA-256 is
`821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`.
It runs on CPU, reranks ten hybrid candidates in batches of 16, and selects five
evidence records.

Generation uses the official `Qwen/Qwen3-4B-GGUF` repository at revision
`bc640142c66e1fdd12af0bd68f40445458f3869b`, file
`Qwen3-4B-Q4_K_M.gguf`. Its required SHA-256 is
`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
The context is 4096 tokens; output is capped at 768 tokens; temperature is 0,
top-p is 1, seed is 42, thinking is disabled, and there are no hidden retries.

## Windows setup

Activate the existing Python 3.12 environment and install the isolated packages:

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[embeddings]"
python -m pip install -e ".\rag\retrieval"
python -m pip install -e ".\rag\reranking[test,models]"
python -m pip install -e ".\rag\generation[test]"
```

Install an official llama.cpp release. One Windows option is:

```powershell
winget install --id ggml.llamacpp --exact
```

Download the pinned GGUF from the frozen Hugging Face revision into the ignored
runtime directory. `huggingface-cli` is not required:

```powershell
New-Item -ItemType Directory -Force .runtime\rag\models | Out-Null
$modelUrl = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf"
Invoke-WebRequest -Uri $modelUrl -OutFile .runtime\rag\models\Qwen3-4B-Q4_K_M.gguf
python -m aegis_rag_generation verify-model --json
```

Do not start the server if checksum verification fails. Start it only on
loopback; tune `--n-gpu-layers` downward to `0` for CPU-only fallback:

```powershell
llama-server.exe `
  --model .runtime\rag\models\Qwen3-4B-Q4_K_M.gguf `
  --alias aegis-qwen3-4b-q4km `
  --host 127.0.0.1 --port 8081 `
  --ctx-size 4096 --parallel 1 --threads 6 `
  --n-gpu-layers 20 --jinja `
  --chat-template-kwargs '{"enable_thinking":false}'
```

In another terminal, verify health and run a diagnosis:

```powershell
docker compose up -d --wait postgres
python -m aegis_rag_generation model-health --json
python -m aegis_rag_generation diagnose --query "Why is checkout latency high after a database connection-pool alert?" --json
python -m aegis_rag_generation smoke --json
```

The real smoke report is written under ignored
`.runtime/rag/generation/real-smoke-report.json`. Stop `llama-server.exe` after
validation; it is intentionally absent from Docker Compose.

## Reranking benchmark discipline and results

`reranking_queries_v1.jsonl` contains 30 queries that are distinct from the
Phase 9 benchmark. Twenty development queries and ten final queries are balanced
across five incident families and query styles. The 60 qrels were manually
resolved against the frozen 65-chunk corpus. Benchmark
`reranking-v1-36c7394661c8` freezes query, qrel, configuration, corpus, retrieval,
and model identities. The final report is write-once.

Development NDCG@5 moved from 0.7763 to 0.7341; this regression was retained and
no tuning followed. On the one-time final split, NDCG@5 moved from 0.7302 to
0.7833, NDCG@10 from 0.7578 to 0.8014, Recall@5 from 0.6500 to 0.7000, and
MRR@10 remained 0.9000. These ten final queries are a small holdout and do not
establish broad production quality.

Warmed CPU reranking of ten passages measured 87.45 ms p50, 110.95 ms p95,
112.08 ms p99, and 92.25 ms mean. Retrieval plus reranking measured 108.84 ms
p50. The final process loaded the cached reranker in 0.224 seconds.

## Functional generation smoke and resources

Eight real cases covered known dependency, memory, CPU, startup, latency, two
insufficient-evidence cases, and adversarial retrieved instructions. All eight
returned the expected status and passed schema and citation validation. Total
duration was 91.24 seconds. Individual generation times ranged from 3.67 to
19.01 seconds and reported throughput ranged from 16.61 to 18.57 tokens/second.
The non-streaming validation path does not expose time-to-first-token.

The tested host had a 12-logical-processor Intel CPU and a 4 GB NVIDIA RTX 3050
Laptop GPU. With 20 layers offloaded, observed llama-server peak working set was
about 3.99 GB and peak private bytes about 5.23 GB. Total reported GPU memory use
rose by approximately 1.76 GB from the pre-server reading. These are local
observations, not sizing guarantees.

## Security and failure behavior

- Only plain HTTP origins on `127.0.0.1` or `localhost`, with an explicit port,
  are accepted. No credentials, path, query, or fragment is allowed.
- The model gets no tools, filesystem access, environment dump, remote URL, qrel,
  label, or secret. Generated actions are advisory and are never executed.
- Evidence is delimited as untrusted data. Prompt-like text in retrieved content
  cannot replace system instructions.
- Oversized context drops lowest-ranked whole evidence records; it never slices
  arbitrary evidence text. An irreducible overflow fails explicitly.
- Empty retrieval abstains before generation. Malformed JSON, schema mismatch,
  unknown, missing, or duplicate citations, provider failure, and checksum
  mismatch all fail closed.
- Citation source and heading metadata are reconstructed from the server-side
  evidence map. The model may reference only exact IDs `E1` through `E5`.

## Tests and CI

Hosted CI downloads neither model. It uses deterministic fake embedding,
reranking, and SLM providers while exercising real package contracts and the
reranking PostgreSQL/pgvector integration path:

```powershell
python -m pytest rag\reranking\tests -q
python -m ruff check rag\reranking
python -m pytest rag\generation\tests -q
python -m ruff check rag\generation
```

Phase 11 owns formal semantic, faithfulness, and answer-quality evaluation.
Phase 10 makes no claim about calibrated confidence, production readiness, or
automated remediation.
