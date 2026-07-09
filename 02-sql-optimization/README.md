# Module 02 — SQL Optimization

## Backstory

You've inherited Kupitron, a marketplace database that has been in production
long enough to accumulate every kind of damage: `orders` at 6 million rows
with the wrong indexes for the queries actually run against it,
`order_items` at 13.8 million rows with an index that *looks* right but
isn't, `products` at 2 million rows with unindexed JSONB and no substring
search, `reviews` carrying five indexes nobody can explain, `inventory_events`
at 9 million rows growing unbounded with three tables' worth of vacuum debt
behind it, and a payment-reconciliation worker fleet that serializes on locks
instead of running in parallel. None of this was one dramatic outage — it's
the ordinary residue of years of "just ship it," and now it's your job.

This is priority #1 in this repo's learning path. Fourteen tasks, each
built around one screaming production query or one quietly-decaying piece of
infrastructure, ending in a capstone where you audit the whole database cold,
the way a senior engineer would on day one of owning it.

## Setup

Prerequisites: Docker with compose v2, uv.

```bash
cd 02-sql-optimization
docker compose up -d --wait     # Postgres 16 on port 54302
uv sync
uv run python seed/generate.py  # respects SCALE env (default 1.0); takes a while at full scale
```

Postgres is reachable at `localhost:54302`, db/user/password `sandbox`.
Port is overridable via `SANDBOX_02_PORT`.

`seed/generate.py` deterministically generates the Kupitron dataset (fixed
seed), applies `seed/schema.sql`, bulk-loads via `COPY`, and runs a
mid-seed `ANALYZE` plus an update-churn phase — all deliberate, see the
schema and tasks 07/11 for why. At scale 1.0 it seeds roughly: 1.0M `users`,
2.0M `products`, 6.0M `orders`, 13.8M `order_items`, 3.0M `reviews`, 5.7M
`payments`, 9.0M `inventory_events`. **Do not change `--scale`/`SCALE`** —
every task's checker and baseline assume the default scale-1.0 dataset.

## Shared tooling

Two scripts under `tools/` are shared across every task, run from the module
root:

- **`tools/baseline.py`** — records or compares a machine-local timing
  median. Every timing check in this module is relative to a baseline
  recorded on your own machine, never an absolute millisecond figure —
  hardware varies too much for anything else to be fair. Results go into
  `baseline-local.json` (gitignored) at the module root.

  ```bash
  uv run python tools/baseline.py record queries/q01.sql
  uv run python tools/baseline.py record queries/q01.sql --id q01 --runs 5
  uv run python tools/baseline.py compare my_rewrite.sql --id q01 --min-speedup 20
  ```

  Every run executes inside a transaction that's rolled back afterward, so
  it's safe to time `UPDATE`/`DELETE`-shaped queries too.

- **`tools/plan_check.py`** — structural assertions against an
  `EXPLAIN (ANALYZE, BUFFERS)` plan (node types present/absent, join
  algorithm, worst estimate-vs-actual row error). It's the library each
  task's `tests/check.py` imports, but it also runs standalone:

  ```bash
  uv run python tools/plan_check.py queries/q01.sql \
      --forbid "Seq Scan:orders" --require "Index Scan:orders" \
      --max-estimate-error 100
  ```

  Also safe on data-modifying statements — the `EXPLAIN ANALYZE` it runs is
  always wrapped in a rolled-back transaction.

## How to work

- Work the tasks in order, one at a time. Later tasks build on earlier ones:
  tasks 02 and 04 reuse (and refine) the index you build in task 01; task 13
  is far more pleasant if you've already done task 03. Nothing forces this
  dependency at the tooling level, but skipping ahead means you'll be
  diagnosing extra unrelated slowness.
- Each task's `tests/check.py` is the gate — run it from the module root
  (e.g. `uv run python 01-read-the-plan/tests/check.py`). It must print
  `PASSED` at the end.
- Hints escalate: `hints/hint-1.md` points in a direction, `hint-2.md`
  narrows to a mechanism, `hint-3.md` is close to pseudocode. Try the task
  first.
- Fill in each task's `NOTES.md` after finishing — some checkers verify it's
  non-empty, and it's where you record before/after numbers on tasks like
  11 (vacuum debt) where the checker can't see your reasoning.
- `queries/q01.sql` through `q06.sql` at the module root belong to tasks
  01-06. From task 07 onward, each task carries its own query file(s) inside
  its own `src/` (`given_query.sql`, `page_query.sql`, `claim.sql`, etc.) or,
  for the capstone, `workload/qc01.sql`-`qc08.sql`.

## Warning: spoilers in `.authoring/` and schema comments

`.authoring/` at the module root documents every planted defect and the
intended fix for each task — it is off-limits until *after* you've finished
(and validated) the task in question. The same goes for the header comments
inside `seed/schema.sql`: they mark *where* a defect is, which you'll
inevitably see just reading the schema, but the `.authoring/tasks-w*.md`
notes go further and give away the intended fix. At minimum, don't open
`.authoring/` mid-task.

## Tasks

| # | Task | What it's about | Evenings |
|---|------|------------------|----------|
| 01 | read-the-plan | diagnose a 6M-row `orders` lookup via `EXPLAIN`, fix with the right composite index | 1 |
| 02 | support-dashboard | range-predicate aggregate over `orders`; decide whether task 01's index already covers it or a new one is needed | 1 |
| 03 | order-detail-join | figure out why an index containing `order_id` on `order_items` still isn't used, fix the column order | 1 |
| 04 | index-only-scan | build a covering index and understand `Index Scan` vs. `Index Only Scan` and `Heap Fetches` | 1 |
| 05 | jsonb-containment | index JSONB `@>` containment on `products.attrs` with a GIN index | 1 |
| 06 | trigram-search | fix a leading-wildcard `ILIKE '%term%'` search with `pg_trgm` trigram indexing | 1 |
| 07 | planner-blindspots | diagnose a stale-statistics-driven bad plan on `orders.status`, fix with `ANALYZE`/statistics target | 1-2 |
| 08 | index-audit-reviews | audit five indexes on `reviews` against a documented read workload, drop the redundant ones | 1-2 |
| 09 | deep-pagination | replace an `OFFSET`/`LIMIT` deep-page query on `inventory_events` with keyset pagination | 1 |
| 10 | partition-the-firehose | migrate `inventory_events` to monthly `PARTITION BY RANGE` for pruning and fast retention | 1-2 |
| 11 | vacuum-debt | quantify and remediate vacuum debt on three tables with disabled autovacuum | 1 |
| 12 | worker-lock-queue | fix a payment-reconciliation claim query that serializes workers via row locks, using `FOR UPDATE SKIP LOCKED` | 1-2 |
| 13 | kill-the-n-plus-one | rewrite a 1+2*N query dashboard fetch into a constant number of set-based queries | 1 |
| 14 | capstone-full-audit | **capstone** — cold audit of the whole reset database, 8 workload queries, written report | 2-4 |

The capstone (14) starts from a deliberately fresh reseed — `docker compose
down -v && docker compose up -d && uv run python seed/generate.py` — which
destroys any fixes you applied in tasks 01-13 on that same database. That's
by design: it audits the database as if seeing it for the first time. Work
it through its three checkpoints, each with its own validator:

- **CP1 — diagnose and baseline**: `EXPLAIN` every workload query, record a
  timing baseline for each, and fill in `REPORT.md` sections 1-4 (inventory,
  triage, defect-family mapping, prioritized fix plan).
- **CP2 — fix the hot paths**: apply fixes until every query's plan is
  structurally sound and clears its SLA, and update `REPORT.md` section 5
  with before/after numbers.
- **CP3 — hygiene and report**: clean up vacuum debt, stale statistics, and
  redundant indexes; finish `REPORT.md` sections 6-8.

## Teardown

```bash
docker compose down -v
rm -rf data/
```
