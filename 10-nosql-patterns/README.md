# 10 — NoSQL patterns

## What this module covers

You run a scraper. The problems it throws off are not "store a row and read it
back" problems — they are coordination and shape problems: don't hammer a shop
past its rate limit, don't let two workers scrape the same page at once, don't
re-scrape a url you already saw, hand work off through a durable queue, and
store documents whose fields genuinely vary from one to the next. This module
works through those with the two engines built for them:

- **Redis beyond cache** — an atomic concurrent rate limiter, a distributed
  lock with a fencing token and a safe compare-and-delete release, exact-set
  vs Bloom-filter dedup (RedisBloom `BF.*`), and Redis Streams consumer groups
  with acknowledgement and dead-consumer reclaim.
- **MongoDB vs Postgres JSONB** — the same semi-structured workload modeled
  both ways: embed vs reference, Mongo indexes vs Postgres GIN, aggregation
  pipelines, so you can judge when "just use JSONB" is right and when it isn't.

Two datasets carry the module: a corpus of semi-structured scraped **product
documents** and a stream of scrape **events**.

## Stack

Three services via `docker-compose.yml` (Docker + compose v2, and `uv`):

- **redis** — `redis/redis-stack-server:7.4.0-v3` (bundles the RedisBloom
  module for `BF.*`, which task 03 needs). Host port `6310`, no password.
- **mongodb** — `mongo:7` on host port `27310`. User/password
  `sandbox`/`sandbox` (auth DB `admin`), database `sandbox`.
- **postgres** — `postgres:16` on host port `54310`. DB/user/password all
  `sandbox` (used by task 06, the JSONB side).

Ports are overridable via `SANDBOX_10_REDIS_PORT`, `SANDBOX_10_MONGO_PORT`,
`SANDBOX_10_PG_PORT`.

```bash
cd 10-nosql-patterns
uv sync
docker compose up -d          # wait for all three healthy: docker compose ps
uv run python generate.py
```

## Data generation

`generate.py` builds both corpora deterministically (products seed `10101`,
events seed `10102`, vectorized numpy) and writes them as **NDJSON** (one JSON
object per line) to `data/products.json` and `data/events.json`. It also writes
`data/ground-truth.json` — the committed answer key every validator grades
against — computed purely from the numpy/python arrays, independent of any
database. **No database is loaded by `generate.py`**: each task loads Redis /
Mongo / Postgres itself, since the tasks load differently.

- `data/products.json` — semi-structured product documents. `specs` keys depend
  on category and are randomly absent (~20%), `seller` is an embedded
  sub-document, `tags` is a multikey array. Feeds tasks 05, 06.
- `data/events.json` — scrape hits, each re-observing a real catalog product,
  with a known ~30% duplicate-url rate and Zipf-skewed domains. Feeds tasks
  01–04 and the capstone.

`SCALE` (env, default `1.0`) sizes both: `n_products = 20000`,
`n_events = 25000` at scale 1.0. These are small on purpose — the point here
is shape and coordination, not volume.

```bash
SCALE=0.1 uv run python generate.py   # light run
```

Everything under `data/` is gitignored except `ground-truth.json`.

## Tasks

- **01** — rate-limiter (Redis): an atomic concurrent rate limiter.
- **02** — distributed-lock (Redis): `SET NX PX` lock, fencing token, safe
  compare-and-delete release.
- **03** — dedup-filter (Redis): exact `SET` vs Bloom filter (`BF.*`) for
  seen-url dedup.
- **04** — redis-streams-consumer (Redis Streams): consumer group, `XACK`,
  reclaim a dead consumer's pending via `XAUTOCLAIM`/`XPENDING`.
- **05** — mongodb-document-modeling (Mongo): embed vs reference, indexes, an
  aggregation pipeline over the semi-structured docs.
- **06** — mongodb-vs-jsonb (Mongo + Postgres JSONB): the same workload both
  sides, GIN vs Mongo indexes.
- **07** — nosql-decision-writeup (written).
- **08** — capstone: a scrape-ingestion control-plane combining the rate
  limiter, lock, dedup, a Redis Stream, and Mongo materialization, with
  steady/chaos checkpoints.

## Working on a task

Each task lives in `NN-task-name/` with its own `README.md`, `src/` scaffold,
`tests/`, and `hints/`. Validators import shared helpers from
`harness/common.py` (Redis/Mongo/Postgres clients, `redis_flush_prefix`,
`run_concurrently`, ground-truth loading, benchmark timing) and print
`PASSED` / `NOT PASSED: <reason>`.

```bash
uv run python NN-task-name/tests/validate.py
```

The three services are **shared** across all 8 tasks. Each task confines its
state to a namespace so validators never collide: Redis keys under `s10:tNN:`,
Mongo collections prefixed `tNN_`, and (task 06) a Postgres schema `t06`.
Validators clean their own namespace on setup and never `FLUSHALL`.

## `.authoring/` is off-limits until after a task

`.authoring/` holds spoilers — the full data contract, RNG draw order,
ground-truth internals, the namespacing convention, and the design rationale
behind every task. Read it *after* finishing a task, never before.
