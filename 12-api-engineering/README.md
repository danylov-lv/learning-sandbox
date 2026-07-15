# 12 — API engineering

## What this module covers

You already build FastAPI/NestJS services and ship them behind queues and
k8s. What this module drills is the layer where an API stops being a demo
and starts surviving production traffic: pagination that doesn't fall over
at depth, a cache that is fast AND never lies, a rate limiter that holds
under real concurrency (not just a sequential burst), background jobs that
are actually idempotent under a retry storm, and exports that stream instead
of quietly materializing 200,000 rows in memory. Then a dedicated security
block — SQL injection (break your own endpoint, then fix it two layers
deep), JWT auth with refresh rotation and reuse detection, and secrets
management (scanning a repo's history for leaked credentials, docker
`secrets:` instead of plaintext env vars) — followed by a load-test task
where you're handed a working endpoint and have to find why it falls over
under concurrency with no docstring telling you where to look. The capstone
recombines pagination, caching, rate limiting, and auth into one hardened
service that also has to survive Redis going down.

**This module runs its own stack — it does NOT sit on top of module 02's
database.** Module 02's Postgres is deliberately wrecked (missing indexes,
bloat, bad types) as ITS OWN curriculum; reusing it here would contaminate
every pagination/caching benchmark in this module with unrelated missing-
index noise. Module 12 seeds the same marketplace domain (sellers,
categories, products, users, orders, order_items) into a clean, properly
indexed schema (`shop`) in its own containers, fully independent of module
02's lifecycle. See `.authoring/design.md`'s "Own stack, not module 02's"
section for the full rationale.

## Stack

Its own `docker-compose.yml`, at the module root:

| Service  | Image        | Host port | Env var                 |
|----------|--------------|-----------|--------------------------|
| Postgres | `postgres:16`| 54312     | `SANDBOX_12_PG_PORT`     |
| Redis    | `redis:7`    | 6312      | `SANDBOX_12_REDIS_PORT`  |

Task apps (FastAPI/uvicorn) run on the host, not in compose, always on an
OS-assigned ephemeral port — there is no fixed API port, so parallel task
runs never collide.

## Getting started

```bash
cd 12-api-engineering
docker compose up -d
uv sync
uv run python generate.py
```

`generate.py` seeds the shared, read-only `shop` corpus: 200,000 products,
500,000 orders, ~1.19M order_items, 20,000 users — about 60s and ~259MB at
the default `SCALE=1.0`. Set `SCALE` to shrink it for a lighter local run
(e.g. `SCALE=0.05`), and `GROUND_TRUTH_ONLY=1` to just recompute/rewrite
`data/ground-truth.json` without touching Postgres — fast, no DB required.
No task ever writes to `shop`; each task that needs writable state owns its
own Postgres schema (`t04`, `t06`, `t07`, ...) or Redis key prefix
(`s12:tNN:`).

## Tasks

- **01** — pagination-offset-vs-cursor: build both `LIMIT/OFFSET` and
  keyset (cursor) pagination over 200k products, then benchmark on your own
  machine to prove offset pagination does linearly more work with depth
  while cursor pagination stays flat.
- **02** — response-caching-redis: cache-aside a category summary
  aggregation in Redis with a TTL and an explicit invalidation route — the
  cached path must be both dramatically faster AND byte-for-byte correct.
- **03** — rate-limiting-and-quotas: an atomic (single Redis round-trip)
  per-key rate limit plus a longer-window quota in front of a public search
  endpoint, correct under a genuinely concurrent burst, not just sequential
  calls.
- **04** — background-jobs-and-idempotency: an "export my order history"
  endpoint that enqueues and returns immediately, where repeated or
  concurrent requests sharing an `Idempotency-Key` all resolve to the exact
  same job — enforced by a Postgres unique constraint, never a check-then-
  insert race.
- **05** — streaming-large-exports: an NDJSON catalog export that streams
  from Postgres to the socket via a bounded batch/cursor at every layer, so
  peak memory stays flat as the export grows instead of scaling with row
  count.
- **06** — sql-injection: a real, working, deliberately vulnerable search
  endpoint (string-interpolated SQL) — exploit it, then fix it two layers
  deep: parametrized queries plus a least-privilege Postgres role that
  can't reach `shop.users` even if the query layer regresses.
- **07** — auth-jwt-and-refresh: RS256 JWT login/refresh/`/me`, with a trap
  battery covering `alg: none`, algorithm confusion, tampered/expired
  tokens, and refresh-token rotation with reuse detection that revokes the
  whole token chain, not just the replayed call.
- **08** — secrets-management: a scanner that finds leaked credentials in
  both a repo's working tree and its full git history (with realistic
  decoys that must not be flagged), plus converting a compose file's
  plaintext password to the docker `secrets:`/`*_FILE` convention.
- **09** — load-test-and-bottleneck-hunt: handed a shipped, working
  `/catalog/{category_id}` endpoint with no hints, find why it falls over
  under concurrency (measure, hypothesize, fix one thing, re-measure) and
  raise throughput/p95 without changing a single byte of its response.
- **10** — capstone-catalog-api: recombine cursor pagination, cache-aside,
  rate limiting, and JWT auth into one service, then harden it — SQLi
  battery, forged/rotated tokens, a concurrent cache-invalidation race, and
  Redis going down entirely — across three checkpoints (CP1 steady state,
  CP2 chaos/hardening, CP3 design memo + a green re-run of CP1+CP2).

## Running a task's validator

Run from the **module root**, not the task directory:

```bash
uv run python 01-pagination-offset-vs-cursor/tests/validate.py
```

Tasks 01, 02, and 09 make relative timing claims and need a machine-local
baseline recorded first:

```bash
uv run python 01-pagination-offset-vs-cursor/baseline.py
uv run python 02-response-caching-redis/baseline.py
uv run python 09-load-test-and-bottleneck-hunt/baseline.py
```

Each validator prints `PASSED` or `NOT PASSED: <reason>` and never trusts
your app's own output as ground truth — it recomputes an oracle from `shop`
directly (or from the committed `data/ground-truth.json`) and checks your
API's output against that.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` holds the harness API contract, the `shop` schema,
the corpus RNG draw order, and the committed ground-truth values — spoilers
for every task in this module. Read it after finishing a task, never before.
