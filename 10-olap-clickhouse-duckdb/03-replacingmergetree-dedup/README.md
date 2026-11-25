# 03 -- ReplacingMergeTree and the Cost of "Eventually Deduped"

## Backstory

Your scraper doesn't always ingest cleanly. A retry after a timeout, an
overlapping backfill window, a re-run of yesterday's job -- any of these can
re-land the SAME observation, the same `(product_id, seller_id, scraped_at)`,
more than once. Each re-ingest is stamped with an increasing `version` and
`ingested_at`, and the LATEST version is the one that's actually true; the
rest are noise. You don't want to run a nightly batch job that scans
everything and deletes the losers -- you want the table itself to converge
to "one row per key, the newest one" as new data lands, and you want to be
able to read the CURRENT state at any moment, not just after some cleanup
job has run.

`ReplacingMergeTree(version)` is ClickHouse's answer: rows that share the
table's `ORDER BY` key get collapsed down to one during background merges,
keeping whichever row has the highest value in the named version column.
That sounds like it solves the problem outright -- until you notice the
word "background". Merges are asynchronous, ClickHouse decides when to run
them, and there is no guarantee one has happened by the time you go looking
at the table. Insert a duplicate batch and immediately run `SELECT *`, and
you might see every duplicate still sitting there in separate unmerged
parts -- or you might see exactly one row per key, if a merge happened to
already run. Same table, same engine, two different answers, and nothing in
the query told you which one you got. A correct read cannot assume the
merge already happened; it has to force correctness itself, either with
`FINAL` or with an explicit aggregation over whatever rows currently exist.

This task makes you build both sides of that story: the table that
(eventually) self-heals, and the read that is right RIGHT NOW regardless of
whether it has.

## What's given

- `src/dedup.py` -- five functions. `create_table` and `insert_batch` take a
  live clickhouse-connect client and actually execute (DDL / INSERT);
  `deduped_state_query`, `count_before_merge`, and `count_after_dedup` each
  return a SQL string for the validator to run. Rich docstrings on each
  explain the exact contract. All five currently `raise NotImplementedError`.
- `generate.build_duplicate_batch(seed, n)` -- a pure, numpy-only fixture
  (no DB, no dependency on the live 09 corpus) that returns `n` synthetic
  observation rows in which the natural key `(product_id, seller_id,
  scraped_at)` deliberately collides across several rows, each with a
  distinct `version` and a matching `ingested_at`. Rows come back in ingest
  order, NOT grouped by key -- a realistic out-of-order duplicate stream.
- The live stack: ClickHouse HTTP on `localhost:8309`, DB `price_history`,
  user/password `sandbox`/`sandbox`. `harness/common.py` gives you
  `ch_client()`, `ch_query()`, `ch_command()`.

## What's required

Implement all five functions in `src/dedup.py`:

1. **`create_table(client)`** -- create `t03_observations_dedup` as a
   `ReplacingMergeTree(version)` over `(product_id, seller_id, scraped_at,
   category, currency, price, in_stock, version, ingested_at)`, `ORDER BY
   (product_id, seller_id, scraped_at)`. Idempotent: drop-if-exists first.
2. **`insert_batch(client, rows)`** -- load a list of row dicts (as returned
   by `build_duplicate_batch`) into the table, in the order given.
3. **`deduped_state_query()`** -- a SELECT returning one row per natural key
   (product_id, seller_id, scraped_at, price, in_stock, version) reflecting
   the CURRENT (highest-version) state, correct whether or not a background
   merge has run.
4. **`count_before_merge()`** -- raw row count, duplicates included.
5. **`count_after_dedup()`** -- distinct natural-key count.

The crux of the task is function 3. You'll need to decide between `FINAL`
and an `argMax(...)`-based `GROUP BY`, and be able to explain the tradeoff
-- that's what this task's NOTES.md asks you to record.

Try it by hand before trusting the validator (see `src/dedup.py`'s module
docstring for a worked-out snippet), and in particular try a PLAIN `SELECT *
FROM t03_observations_dedup` (no FINAL, no GROUP BY) right after inserting --
watch it potentially return duplicate rows, or a stale version, proving a
naive read is not safe.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Builds a deterministic duplicate batch (`build_duplicate_batch(903,
  6000)`, ~2000 distinct keys, ~3 versions per key) and computes, in plain
  Python, the expected highest-version survivor for every key.
- Drops any leftover `t03_*` table, calls your `create_table` and
  `insert_batch`.
- Asserts `count_before_merge()` equals the exact number of rows inserted
  (nothing silently dropped or collapsed at insert time -- collapsing only
  ever happens at merge/query time, never on INSERT).
- Asserts `count_after_dedup()` equals the exact number of distinct natural
  keys.
- Runs `deduped_state_query()` and asserts it returns exactly one row per
  key, and that EVERY key's version, price, and in_stock match the
  expected highest-version survivor exactly (price within `1e-6`) -- this is
  the proof that your read is correct independent of merge timing, run
  immediately after insert with no wait and no forced `OPTIMIZE`.
- Drops `t03_*` in a `finally` block, whether the run passed or failed.

Fails cleanly (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack is
down, a function still raises `NotImplementedError`, a count is off, or a
single key's survivor is wrong.

## Estimated evenings

1

## Topics to read up on

- `ReplacingMergeTree(version)`: what it does, and specifically what it does
  NOT do -- it does not enforce uniqueness, does not deduplicate
  synchronously on INSERT, and does not guarantee WHEN a merge collapsing
  duplicates will run
- The `ORDER BY` clause as the dedup key: rows collapse only when they share
  every ORDER BY column
- `FINAL`: what it costs (merging matching parts at query time, on every
  query) versus what it buys you (correctness with zero extra SQL logic)
- `argMax(column, version)` (and `max(version)`) as a `GROUP BY`-based
  alternative that doesn't depend on the table engine's merge semantics at
  all -- when you'd prefer this over `FINAL`
- Why background merges in ClickHouse are asynchronous and untimed by
  design, and what that implies for anything that reads a
  ReplacingMergeTree table without FINAL/argMax immediately after a write
- `optimize_on_insert` (default on): ClickHouse can collapse duplicate-key
  rows WITHIN a single insert block before the part ever hits disk -- a
  second, insert-time mechanism distinct from background merges, and one
  this task's `insert_batch` has to explicitly account for

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module, including the
exact `build_duplicate_batch` contract -- spoilers. Don't read it before
finishing this task.
