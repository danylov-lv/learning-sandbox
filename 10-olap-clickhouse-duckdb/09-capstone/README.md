# 09 -- Capstone: Serving Layer

## Backstory

Every task before this one proved one mechanism in isolation: the sparse
primary index (01), a materialized view accumulating a rollup incrementally
(02), `ReplacingMergeTree` dedup (03), TTL lifecycle (04), ClickHouse against
Postgres at 50M rows (05), DuckDB reading a Parquet lake directly with
partition pruning (06), DuckDB against ClickHouse head to head (07), and a
written decision memo on when each engine earns its keep (08). None of those
had to survive being combined into something you'd actually stand up for a
team that wants to query the scraped price history.

This capstone is that: an analytical serving layer for `price_history`,
built on both engines, with a design memo defending the choices at the end.
Three checkpoints, most likely three separate evenings:

- **CP1** -- stand up the ClickHouse side: an incremental per-(day,
  category) rollup fed by a landing table and a materialized view (same
  shape as task 02), plus three direct aggregate answers a dashboard would
  actually ask for (`total_price_sum`, `per_category_instock`,
  `top_sellers`).
- **CP2** -- cross-check every one of those aggregates with DuckDB reading
  the Parquet lake directly, no server at all (task 06's territory), plus
  reconfirm the lake's partition pruning still holds.
- **CP3** -- write `DESIGN.md`, defending the ORDER BY choices, the
  materialized-view-vs-on-demand call, where ReplacingMergeTree/TTL would
  fit if this scraper started sending corrections, when you'd actually run
  a ClickHouse server for this versus just pointing DuckDB at the lake, and
  what changes at 50-500x the row count -- then confirm CP1 and CP2 still
  both pass.

## What's given

- `src/build.py` -- CP1 scaffold, five functions with rich docstrings, all
  `raise NotImplementedError`: `create_rollup`, `rollup_query`,
  `total_price_sum`, `per_category_instock`, `top_sellers`.
- `src/lake_check.py` -- CP2 scaffold, four functions: `total_price_sum`,
  `per_category_instock`, `top_sellers` (same three shapes as CP1, now over
  the lake), and `one_category_files` (the pruning proof).
- `DESIGN.md` -- the CP3 template, five required `##` sections, each with a
  `(fill in -- ...)` prompt.
- `tests/validate_cp1.py`, `tests/validate_cp2.py`, `tests/validate_cp3.py`
  -- the three checkpoint validators. `tests/validate.py` -- a runner that
  invokes all three in order and reports a summary.
- The live stack: ClickHouse HTTP on `localhost:8309`, Postgres on
  `localhost:54309`, and the Parquet lake under `data/parquet/`, all
  coherent with `data/ground-truth.json`. `harness/common.py` for
  `ch_client()` / `ch_query()` / `ch_command()` / `duckdb_connect()` /
  `parquet_glob()` / `load_ground_truth()`.

## What's required

**CP1.** Implement all five functions in `src/build.py`:

1. `create_rollup(client)` -- idempotently create `t09_landing` (empty
   MergeTree, same 8 columns as `observations_raw`), `t09_daily_category`
   (`SummingMergeTree` or `AggregatingMergeTree`, keyed by `(day, category)`),
   and `t09_daily_category_mv` (the materialized view wiring the two
   together, incrementally maintaining `count` + `price_sum` per key).
2. `rollup_query()` -- SQL reading `t09_daily_category` back out fully
   collapsed, correct regardless of whether a background merge has run.
3. `total_price_sum(client)` -- grand total price sum, direct aggregate over
   `observations_raw`.
4. `per_category_instock(client)` -- count + avg(price) per category, over
   `in_stock` rows.
5. `top_sellers(client)` -- top 10 `[seller_id, count]` by observation count
   descending, ties broken by `seller_id` ascending.

Run `uv run python tests/validate_cp1.py`. It drops leftover `t09_*`
objects, calls your `create_rollup`, streams `observations_raw` into
`t09_landing` across 5 batches (exercising the view incrementally, exactly
like task 02), and checks all five functions against ground truth. Tears
down `t09_*` in a `finally`, pass or fail.

**CP2.** Implement all four functions in `src/lake_check.py`, each querying
`read_parquet(parquet_glob(), hive_partitioning=true)` over the Parquet
lake -- no ClickHouse involved:

1. `total_price_sum(con)`, `per_category_instock(con)`, `top_sellers(con)`
   -- same three shapes as CP1, now computed by DuckDB over the lake. Both
   CP1 and CP2 are graded against the same ground truth, so agreement with
   ground truth on both sides necessarily proves the two engines agree with
   each other.
2. `one_category_files(con, category)` -- the distinct source file path(s)
   DuckDB reads when filtering to one category (task 06's pruning proof,
   reused here).

Run `uv run python tests/validate_cp2.py`. It opens a DuckDB connection,
checks all four functions against ground truth (and the single-file pruning
proof for `electronics`), and fails cleanly if no lake is found on disk.

**CP3.** Fill in every section of `DESIGN.md`, grounded in what CP1 and CP2
actually showed you, and in the ClickHouse-vs-DuckDB tradeoffs task 08 asked
you to articulate. Run `uv run python tests/validate_cp3.py` -- it checks
the memo is filled in (every section present, no leftover `(fill in`
placeholder, each section substantive), then re-runs CP1 and CP2 as
subprocesses and requires both to still exit 0.

Try each checkpoint by hand before trusting its validator -- open a
ClickHouse client, call `create_rollup`, insert a batch or two into
`t09_landing` yourself; open a DuckDB connection and query the lake
directly.

## Completion criteria

All three green:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
```

or the runner, which does the same three in order and summarizes:

```bash
uv run python tests/validate.py
```

Every validator prints `PASSED` or `NOT PASSED: <reason>` and exits 0/1; no
raw tracebacks. CP3 will not pass while CP1 or CP2 is broken, and it will
not pass on an unfilled `DESIGN.md` even if both checkpoints are green.

## Estimated evenings

3-4 (CP1 is where most of the design decisions get made; CP2 is comparatively
quick if task 06 is still fresh; CP3 is the writeup, but it also forces you
back into CP1/CP2 if anything regressed while you were working on it).

## Topics to read up on

- Materialized views as insert triggers, and why they need a landing table
  rather than pointing directly at an already-populated fact table
- `SummingMergeTree` vs `AggregatingMergeTree` for a plain additive rollup
- Reading a correct answer out of an unmerged rollup table: `GROUP BY ...
  sum()` / `-Merge()` combinators, independent of background merge timing
- Hive partition pruning in DuckDB's `read_parquet(..., hive_partitioning=
  true)`, and how to prove it happened (`filename=true`)
- Why two independent engines agreeing with a shared ground-truth answer key
  is a stronger correctness proof than either engine agreeing with itself
- Tying a design memo's claims to numbers you actually measured, not
  first-principles reasoning alone

## `.authoring/` is off-limits

`.authoring/` (at the module root) holds this module's full data contract,
RNG draw order, and ground-truth internals -- spoilers for every task in the
module, including this one. Don't read it until after you've finished.
