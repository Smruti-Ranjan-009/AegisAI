# Phase 11: End-to-End RAG and SLM Evaluation

Phase 11 evaluates the frozen Phase 10 local diagnosis pipeline. It does not
tune the retriever, reranker, prompt, generator, corpus, or generation
parameters. Results are offline research measurements over a controlled corpus,
not production quality claims.

## Evaluation boundary

```text
query -> BGE dense + PostgreSQL full-text search -> RRF top 10
      -> MiniLM cross-encoder -> top-5 evidence
      -> grounded_incident_v1 -> local Qwen3-4B Q4_K_M
      -> schema/citation validation -> independent scoring
```

Generation and scoring are separate. Gold answers never enter retrieval,
reranking, prompting, or generation. Adversarial overlays are applied only
after retrieval as explicitly delimited, untrusted evidence and are never
inserted into PostgreSQL. Final generation artifacts are write-once and bound
to benchmark, pipeline, evaluator, corpus, query, gold, and overlay hashes.

## Frozen configuration

The machine-readable contract is
[`phase11_pipeline_config.json`](../rag/evaluation/phase11_pipeline_config.json).
Its canonical SHA-256 is
`277bd363ff1ebe10bc0a3642de05f88a18194ca7b349da4f93a1608abccf241f`.

| Component | Frozen value |
| --- | --- |
| Corpus | 15 documents, 65 chunks, fingerprint `f5a7d43a5ca429013ef4117b52a36ca68e4b4f4e1d16a6d13e89867f59443b` |
| Dense embedding | `BAAI/bge-small-en-v1.5`, revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, 384 dimensions, CPU |
| Lexical/RRF | BM25 `k1=1.5`, `b=0.75`; candidate depth 20; RRF `k=60` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L6-v2`, CPU; top 10 to top 5 |
| Prompt | `grounded_incident_v1` |
| Generator | `Qwen/Qwen3-4B-GGUF`, pinned revision and Q4_K_M checksum |
| Runtime | llama.cpp `0.6.0-dev` build 11515, loopback only, context 4096, 20 GPU layers, 6 threads |
| Sampling | temperature 0, top-p 1, seed 42, maximum 768 tokens, thinking disabled, no retries |

The committed JSON contains every complete revision and checksum.

## Benchmark

The independent benchmark ID is `e2e-rag-v1-b61d8c044a77`. It contains exactly
40 manually authored cases:

| Type | Development | Final | Total |
| --- | ---: | ---: | ---: |
| Grounded | 20 | 10 | 30 |
| Insufficient evidence | 3 | 2 | 5 |
| Adversarial | 2 | 3 | 5 |
| Total | 25 | 15 | 40 |

The 30 grounded cases contain six cases for each of five incident families and
six cases for each of five query styles. The final grounded set contains two of
each. Gold records include graded relevant sections, atomic required facts, and
acceptable actions. Validation resolves every gold section against the corpus
and rejects reused Phase 9/10 query text.

Assets and hashes:

- queries: `79a387332732bcdbe4c33cb4b0e714d62124bd77b4e20979028fcde7c5c5a66a`
- gold: `e54666e11aa89f80263a99fa330ac3b1d14d85018918f5bfb9920fcf406ee567`
- adversarial overlays: `97d6573b15920fb170c8b6e69fa67cc06aa627ac24d221073475206df94415ce`
- evaluator: `caeaea29714f08e5dae58efe8de9e1098d4aadce5fe17a5e50b4c119676bd44e`
- metric definitions: `bdf31859fbd6ccd0167668e145a08e1602934cf4e736264d12a44171af8fd231`

## Evaluators and definitions

Semantic support uses the independently pinned
`cross-encoder/nli-deberta-v3-small` revision
`fa2804872c3b4bd748f38c0185cc85775361e735`, Apache-2.0 license, CPU, and a
512-token pair limit. The weight SHA-256 is
`ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86`.
Labels are explicitly mapped as contradiction, entailment, and neutral. This is
an automated proxy, not a human correctness judgment.

- Retrieval: Recall, Hit Rate, MRR, and NDCG at committed cutoffs.
- Citations: structural validity plus micro precision/recall against all and
  direct-evidence gold sections.
- Claim support: NLI entailment of generated atomic claims by cited evidence.
- Completeness: NLI coverage of required facts and acceptable reference actions.
- Relevance: BGE cosine similarity between the query and generated answer.
- Abstention: grounded/insufficient confusion counts and derived rates.
- Adversarial: schema/citation validity, no sentinel repetition or instruction
  execution, and semantic support must all pass.
- Uncertainty: paired 10,000-resample bootstrap with seed 11042 and 95% intervals.

## Final canonical results

The final split was generated once: 15 cases in 268.148 seconds. Ten ordinary
grounded cases produced valid grounded answers, both insufficient-evidence
cases abstained, one adversarial case produced a structurally valid grounded
answer, and two adversarial cases failed closed on schema/citation validation.

| Metric | Result |
| --- | ---: |
| NLI-supported claims | 22 / 56 (39.29%) |
| Unsupported claims | 34 / 56 (60.71%) |
| Contradicted claims | 5 / 56 (8.93%) |
| Neutral claims | 29 / 56 (51.79%) |
| Summary support proxy | 4 / 11 (36.36%) |
| Structurally valid citation cases | 13 / 15 (86.67%) |
| Gold citation precision / recall | 48.48% / 72.73% |
| Direct-evidence citation precision / recall | 45.45% / 83.33% |
| Required-fact coverage | 10 / 22 (45.45%) |
| Reference-action coverage | 4 / 22 (18.18%) |
| Query/answer similarity | mean 0.8572; median 0.8493 |

The result is weak on semantic support and action completeness. Phase 11
reports that finding; it does not tune around it.

### Retrieval context quality

Metrics below cover the ten ordinary grounded final cases.

| Stage | Recall@1 / @3 / @5 | Hit@1 / @3 / @5 | MRR@5 | NDCG@5 |
| --- | --- | --- | ---: | ---: |
| Hybrid RRF | 0.45 / 0.65 / 0.80 | 0.90 / 0.90 / 1.00 | 0.925 | 0.8220 |
| Reranked | 0.50 / 0.60 / 0.75 | 1.00 / 1.00 / 1.00 | 1.000 | 0.7984 |

The reranker improved first-hit placement but reduced final-set Recall@3/@5
and NDCG@5. No post-hoc tuning was performed.

### Abstention and adversarial behavior

The two expected insufficient-evidence cases both abstained; the ten ordinary
grounded cases did not. This gives 100% supported-answer and unsupported-
abstention rates on a very small final sample. All three adversarial cases
failed the strict all-criteria gate: two failed closed on schema/citation
validation, while one resisted the injected instruction but contained NLI-
unsupported claims. There is no claim of prompt-injection robustness.

### No-reranker ablation

The evaluation-only ablation used Hybrid RRF top-5 evidence and otherwise the
unchanged generator. Across ten paired grounded final cases it produced 26/51
supported claims (50.98%), citation precision/recall of 43.24%/80.00%, required-
fact coverage of 35%, reference-action coverage of 40%, and mean relevance of
0.8602.

Canonical minus ablation paired estimates (95% bootstrap interval):

| Measure | Difference [95% interval] |
| --- | ---: |
| End-to-end seconds | -1.8153 [-6.1428, 2.9770] |
| Citation precision | +0.1750 [-0.1217, 0.4433] |
| Citation recall | -0.1000 [-0.2500, 0.0000] |
| Claim support | -0.1012 [-0.2715, 0.0841] |
| Required-fact coverage | +0.1000 [-0.1500, 0.4000] |
| Relevance | -0.0013 [-0.0161, 0.0127] |

The intervals are descriptive and wide; this small benchmark does not establish
a statistically reliable reranker benefit.

## Performance, determinism, and resources

Canonical final latency: retrieval mean 0.0337 seconds (p95 0.0498), reranking
mean 0.1432 seconds (p95 0.1573), valid generation mean 16.977 seconds (p95
26.572), and total mean 17.717 seconds (p95 26.311). Valid generations averaged
255.85 output tokens and 15.98 tokens/second. Percentiles are descriptive single-
machine measurements over small samples.

The NLI evaluator loaded in 2.020 seconds and processed 111 pairs in 8.578
seconds (12.94 pairs/second); no pair was truncated. Five duplicate generation
runs preserved retrieval, reranking, and evidence IDs in 5/5 cases, but exact
structured JSON in only 2/5 and citation sets in 4/5. Seeded local generation is
therefore not byte-deterministic.

Observed llama.cpp peak working set was approximately 3.71 GB and peak private/
paged memory approximately 9.39 GB. Per-process GPU memory was unavailable, so
none is claimed.

## Failure analysis and manual review

Automated failure tags across final cases were: unsupported claim (11 cases),
missing gold fact (10), reranking regression (3), prompt-injection failure (3),
and schema failure (2). Breakdowns by case, incident family, and query style are
written to ignored runtime reports. The generated `manual-review.csv` contains
15 rows with intentionally empty human fields. No human evaluation was
performed.

## Reproduction

Use Python 3.12 and local model caches. Never point destructive tests at the
development database.

```powershell
conda activate aegis
python -m pip install -e ".\rag\ingestion[embeddings]"
python -m pip install -e ".\rag\retrieval"
python -m pip install -e ".\rag\reranking[models]"
python -m pip install -e ".\rag\generation"
python -m pip install -e ".\rag\evaluation[test,models]"
python -m aegis_rag_evaluation validate --json
python -m aegis_rag_evaluation verify-nli --json
```

Start PostgreSQL and the documented loopback llama.cpp server before generation.
Development runs are regenerable; final generation requires
`--confirm-final` and refuses overwrite:

```powershell
python -m aegis_rag_evaluation generate --split development --variant canonical --json
python -m aegis_rag_evaluation score --split development --variant canonical --json
python -m aegis_rag_evaluation determinism --json

python -m aegis_rag_evaluation generate --split final --variant canonical --confirm-final --json
python -m aegis_rag_evaluation generate --split final --variant no-reranker-ablation --confirm-final --json
python -m aegis_rag_evaluation score --split final --variant canonical --json
python -m aegis_rag_evaluation score --split final --variant no-reranker-ablation --json
python -m aegis_rag_evaluation report --split final --json
```

Runtime artifacts, model caches, reports, local databases, and generated output
remain under ignored `.runtime/`; committed source contains no model weights,
answers, secrets, or production data.

## Validation

The completed local regression passed 28 Phase 11 evaluation tests, 23
generation tests, 15 reranking tests, 21 retrieval tests, and 29 ingestion
tests. Earlier-phase regressions also passed: lifecycle 26, classification 21,
anomaly detection 23, feature engineering 29, telemetry lab 17,
telemetry/ML/RAG services 17/1/1, Java/Testcontainers 37, and Kafka integration
2. The ingestion total includes the new destructive-database safety tests.

Ruff passed every Python scope. The GitHub Actions workflow parsed with 14 jobs,
including the fake-only Phase 11 job; Compose configuration parsed; all six
project images built; the complete stack and all four HTTP health endpoints
passed. A read-only post-regression check confirmed that development PostgreSQL
still held 15 active documents and 65 chunks at the frozen corpus fingerprint.
Validation containers and the network were removed without deleting named
volumes. Hosted GitHub Actions was not run locally.

## Limitations

- The corpus is only 15 documents and 65 chunks and is mostly synthetic.
- The final set has only 15 cases; family/style slices have very small counts.
- Gold facts, actions, and relevance judgments are curated and may contain
  author bias.
- NLI and embedding similarity are imperfect automated proxies for correctness.
- Evaluation is English-only and uses one local quantized Qwen3 4B model.
- Performance comes from one developer machine; small-sample percentiles do not
  predict production capacity.
- No human evaluation, production user traffic, online serving, incident
  integration, automated remediation, or robustness certification is included.
