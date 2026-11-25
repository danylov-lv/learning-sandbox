# Module 03 — PostgreSQL Writes and Transactions

PriceWatch ingests scraped prices in batches. Replays, late observations,
concurrent writers, and failures during ingestion can leave history and
current prices out of sync. Work from individual SQL writes to a loader
that commits price history, current prices, and a batch ledger together.

## Prerequisites

Basic SQL joins, CTEs, and primary and foreign keys are enough. The module
follows SQL Optimization in the [course map](../README.md). It provides its
own schema and PostgreSQL service. Windows with Docker and the repository's
Python tooling is sufficient. There is no external broker or source API.

## Quick start

From the module root, run the following commands.

```shell
docker compose up -d --wait
uv sync
uv run python 01-scoped-dml/tests/validate.py
```

PostgreSQL 16 listens on `127.0.0.1:54321` by default. Set
`SANDBOX_03_WRITES_PORT` before starting Compose and running the validators
to use a different port. The local database, user, and password are
`sandbox`. Validators create and clean up their own schemas. An untouched
task prints `NOT PASSED` until you implement its SQL or Python scaffold.

## Data contract

- An offer is identified by `(source, sku)`. The schema seeds the Cartesian
  product of `market`, `outlet`, and `direct` with SKUs `a` through `d`.
- One observation is identified by `(source, sku, version)`. Prices are
  positive integer cents. Higher versions are newer within an offer.
  Identical observation keys carry identical prices.
- `observations` stores history. For every offer with history, `current_prices`
  stores its highest observed version and corresponding cents. `processed_batches`
  tracks successfully committed input files by a stable batch ID.

## Exercises

| # | Task | Focus | Evenings |
|---|---|---|---|
| 01 | [Scoped DML](01-scoped-dml/README.md) | Write scoped INSERT, UPDATE and DELETE with RETURNING | 1 |
| 02 | [Atomic price write](02-atomic-price-write/README.md) | Commit history and the current price together | 1 |
| 03 | [Savepoints](03-savepoints/README.md) | Recover from rejected optional metadata inside a transaction | 1 |
| 04 | [Idempotent upsert](04-idempotent-upsert/README.md) | Handle repeated and out-of-order observations | 1 |
| 05 | [COPY and staging](05-copy-staging/README.md) | Load a CSV and merge it as a set | 1 |
| 06 | [Isolation and snapshots](06-isolation-snapshots/README.md) | Compare what two sessions see across a commit | 1 |
| 07 | [Row locks and deadlocks](07-row-locks-and-deadlocks/README.md) | Reproduce a deadlock, then fix lock ordering | 1–2 |
| 08 | [Serializable retries](08-serializable-retries/README.md) | Protect a cross-row limit and retry a full transaction | 1–2 |
| 09 | [Capstone — batch loader](09-capstone-batch-loader/README.md) | Ship a replayable loader for overlapping batches | 2–3 |

Tasks have independent scaffolds and fixtures. Use them in order to practice
each technique before combining it in the capstone. The task validators
report data and transaction behavior. They synchronize separate sessions
at known points and observe PostgreSQL lock waits. Timeouts bound failures
in the harness. They do not grade performance.

## Try the completed loader on generated data

From the module root, generate two reproducible batches that overlap, arrive
out of version order, and contain duplicate observations.

```shell
uv run python seed/generate.py
uv run python load_batch.py init
uv run python load_batch.py load batch-a data/batch-a.csv
uv run python load_batch.py load batch-b data/batch-b.csv
uv run python load_batch.py load batch-a data/batch-a.csv
```

Set `SCALE` to change the generated row count and `--output` to change the
generator's output directory. The CLI writes to the persistent `pricewatch`
schema. Initialize it once, then submit batches whose IDs stay associated
with the same input contents. The final command prints `ALREADY APPLIED`
after a successful implementation. The local exercises cover database
behavior across connections and injected application failures on one
primary. They do not model replication, server-crash durability, or
an external acknowledgement protocol.
