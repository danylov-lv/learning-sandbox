# 09 — OLAP: ClickHouse and DuckDB

## What this module covers

You have years of scraped price history — one row per (product, seller,
time) observation — and the row store that served the scraper is the wrong
shape for the questions you now want to ask: per-category averages across
tens of millions of rows, daily rollups, "how did this product's price move
over 180 days". That's an analytical (OLAP) workload, and this module works
through the columnar engines built for it.

The through-line is one fact table, `price_history.observations`, loaded into
three engines over the same data so you can compare them directly:

- **ClickHouse** — MergeTree tables where the `ORDER BY` is a *sparse primary
  index* (part/granule pruning), materialized views for streaming
  aggregation, `ReplacingMergeTree` for dedup, and `TTL` for lifecycle.
- **Postgres** — the OLTP row-store baseline, kept deliberately index-light,
  for a fair "row store vs columnar" contrast at 50M rows.
- **DuckDB** — a zero-server engine that queries a Parquet lake directly.

## Stack

Two services via `docker-compose.yml` (Docker + compose v2, and `uv`):

- **clickhouse** — `clickhouse/clickhouse-server:24.8` (LTS). HTTP on host
  port `8309`, native TCP on `9309`. DB `price_history`, user/password
  `sandbox`/`sandbox`.
- **postgres** — `postgres:16` on host port `54309`. DB `price_history`,
  user/password `sandbox`/`sandbox`, schema `price_history`.

Ports are overridable via `SANDBOX_09_CH_HTTP_PORT`,
`SANDBOX_09_CH_NATIVE_PORT`, `SANDBOX_09_PG_PORT`.

```bash
cd 09-olap-clickhouse-duckdb
uv sync
docker compose up -d          # wait for both healthy: docker compose ps
SCALE=0.02 uv run python generate.py
```

## Data generation

`generate.py` builds the corpus deterministically (seed `90909`, vectorized
numpy) and materializes it into Postgres (`COPY`), ClickHouse
(`insert_arrow` into a MergeTree), and a Hive-partitioned Parquet lake under
`data/parquet/category=<x>/`. It also writes `data/ground-truth.json` (the
committed answer key every validator grades against), computed purely in
numpy independent of any database.

- **`SCALE` controls size. Default `1.0` => 50,000,000 observation rows —
  this is HEAVY** (a full three-sink load takes real time and disk). For
  local work use a light scale:

  ```bash
  SCALE=0.02 uv run python generate.py   # ~1M rows, loads in seconds
  ```

- The committed `data/ground-truth.json` is the **full-scale (50M) answer
  key**. Regenerate it without any DB load — numpy only, seconds — with:

  ```bash
  GROUND_TRUTH_ONLY=1 uv run python generate.py
  ```

- **Coherence note.** Running `generate.py` at scale `X` loads all three
  sinks *and* rewrites `data/ground-truth.json` to match scale `X`. So to
  run a task's validator against a live stack, generate at your chosen
  `SCALE` first (stack and ground truth then agree). Before committing,
  restore the full-scale answer key with `GROUND_TRUTH_ONLY=1` (SCALE=1.0).
  Everything under `data/` is gitignored except `ground-truth.json`.

## Running a task

Each task lives in `NN-task-name/` with its own `README.md`, `src/`
scaffold, `tests/`, and `hints/`. Validators import shared helpers from
`harness/common.py` (ClickHouse/Postgres/DuckDB clients, the `ch_read_rows`
pruning probe, ground-truth loading, benchmark timing) and print
`PASSED` / `NOT PASSED: <reason>`.

```bash
uv run python NN-task-name/tests/validate.py
```

## Planned task lineup

- **01** — mergetree-and-primary-index
- **02** — materialized-views
- **03** — replacingmergetree-dedup
- **04** — ttl-and-lifecycle
- **05** — postgres-vs-clickhouse-50m
- **06** — duckdb-on-parquet
- **07** — duckdb-vs-clickhouse
- **08** — when-clickhouse-when-duckdb (writeup)
- **09** — capstone

## `.authoring/` is off-limits until after a task

`.authoring/` holds spoilers — the full data contract, RNG draw order,
ground-truth internals, and the design rationale behind every task. Read it
*after* finishing a task, never before.
