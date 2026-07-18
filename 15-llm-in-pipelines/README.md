# 15 — LLMs in Pipelines

## What this module covers

Using a local Ollama-served 7B model as a PIPELINE COMPONENT, not a chat
toy: structured extraction from messy HTML, record classification and
enrichment, embedding-based deduplication, and a mini retrieval-augmented-
generation lookup over the sandbox's own docs. Everything runs locally
against `qwen2.5:7b-instruct` (chat/extraction) and `nomic-embed-text`
(embeddings) — no hosted API dependency required to complete the module.

The LLM client is built swappable from the start: every task codes against
`harness/llm.py`'s provider-agnostic interface, and pointing the whole
module at a cloud API instead of local Ollama is a single
`LLM_PROVIDER=openai` environment variable change, never a code change.

Six tasks: a foundational resilience wrapper around the raw LLM client
(retry, reask-on-invalid-output, provider fallback), then four independent
pipeline-component tasks (extraction, classification+enrichment, dedup,
mini-RAG), capped by a capstone that composes all four into one enrichment
pipeline with a quality gate.

## Stack

Its own `docker-compose.yml`, at the module root:

| Service | Image | Host port | Env var |
|---|---|---|---|
| Ollama (HTTP API) | `ollama/ollama:latest` | 11439 | `SANDBOX_15_OLLAMA_PORT` |

## Getting started

```bash
cd 15-llm-in-pipelines
uv sync
uv run python generate.py                # builds data/*.json + data/corpus/*.md + ground-truth.json
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:7b-instruct
docker compose exec ollama ollama pull nomic-embed-text     # once only, models persist in the named volume
```

`generate.py` is deterministic (fixed seed, no external randomness) and
writes the gitignored task inputs — `data/extraction.json`,
`data/classification.json`, `data/dedup.json`, `data/corpus/*.md` — plus
the committed `data/ground-truth.json` summary every task's validator
checks itself against.

Every task imports shared plumbing from `harness/common.py` (pass/fail
helpers, `require_client()` for LLM readiness, precision/recall/F1/
clustering-agreement metrics, loose price/text normalization) and
`harness/llm.py` (the swappable `LLMClient` — `get_client()`, `generate`,
`chat`, `embed`, `cosine`). Validators print `PASSED` or
`NOT PASSED: <reason>` and never leak a raw traceback; an unreachable
Ollama server is reported as an actionable infra message, not a confusing
metric failure.

## Tasks

| # | Task | Status |
|---|------|--------|
| 01 | swappable-llm-client | pending |
| 02 | structured-extraction | pending |
| 03 | classification-and-enrichment | ready |
| 04 | embedding-dedup | pending |
| 05 | mini-rag | pending |
| 06 | capstone (CP1/CP2/CP3) | pending |

## Verification philosophy

- **`require_client()` gates every LLM-dependent validator** before it
  trusts any model output, so "Ollama isn't running" and "your solution is
  wrong" never look like the same failure.
- **Metric thresholds are tuned for a 7B model's real, imperfect
  performance** at `temperature=0`, with headroom for run-to-run sampling
  variance (llama.cpp batching/CUDA nondeterminism means even greedy
  decoding isn't perfectly reproducible across machines).
- **A constant/degenerate baseline always fails** each task's metric
  threshold — majority-class prediction fails classification's macro-F1,
  all-one-cluster and all-singleton both fail dedup's pairwise F1.
- **Gold is always recomputed independently** by calling `generate.py`'s
  `build_*` functions directly against the committed seed — never read back
  from a file the learner's own code could have touched.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` holds spoilers: the full harness API contract, the
dataset schema and generator draw order, the committed ground-truth values,
and the per-task verification philosophy. Read it *after* finishing a task,
never before.
