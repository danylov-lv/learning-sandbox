# 05 -- Postgres vs ClickHouse at 50M Rows

## Backstory

You inherited a scraper that has been writing price observations straight
into Postgres for years -- `price_history.observations`, one row per
(product, seller, time) sample, now sitting at 50M rows. That table is
tuned for what the scraper needs: insert a row, look one up by
`observation_id`. It has exactly one index, the primary key, and nothing
else.

Now analytics wants a number the scraper never needed: for every category,
over rows currently in stock, how many observations are there and what's
the average price? There's no index on `category` or `in_stock` to help --
whatever plan Postgres picks has to visit the heap. Before reaching for
"just add an index", you've been asked to first measure how the SAME
question performs on a columnar engine loaded with the SAME data, so the
team can decide whether the future of this workload is "index the OLTP
store harder" or "stand up something built for this shape of query". This
task is that measurement, done honestly: same data, same question, two
storage models, and a look at *why* they perform the way they do -- not
just a number.

## What's given

- `src/compare.py` -- a scaffold with two functions, `pg_answer(conn)` and
  `ch_answer(client)`, both currently `raise NotImplementedError`. Their
  docstrings pin down the exact contract: both must return
  `{ category: (count, avg_price) }` over in-stock rows, `count` an int,
  `avg_price` a float.
- `baseline.py` -- once both functions work, run it to time each engine on
  this machine and record the numbers to a gitignored
  `baseline-local.json`.
- The live stack: Postgres on `localhost:54309`
  (`price_history.observations`, PK-only), ClickHouse HTTP on
  `localhost:8309` (`price_history.observations_raw`, a MergeTree).
  `harness/common.py` gives you `pg_connect()`, `ch_client()`, `ch_query()`,
  `time_it()`, and the ground-truth loader.
- `data/ground-truth.json` -- the committed answer key. Its
  `per_category_instock` block is exactly this task's benchmark answer.

**On scale.** This task is framed at 50M rows -- that's what
`data/ground-truth.json` ships at, and what the numbers in the docstrings
are drawn from. Loading 50M rows into both engines locally is heavy; for
day-to-day work against a live stack, generate at a light `SCALE` per the
module README (e.g. `SCALE=0.02`) and let `generate.py` rewrite the ground
truth to match. The question and the code you write are identical at any
scale; only the row count -- and the drama of the timing gap -- changes.

## What's required

Implement both functions in `src/compare.py`:

1. **`pg_answer(conn)`** -- query `price_history.observations` in Postgres,
   aggregate `count(*)` and `avg(price)` grouped by `category`, filtered to
   `in_stock` rows. Do the aggregation in SQL, not by pulling rows into
   Python.
2. **`ch_answer(client)`** -- the same question against
   `observations_raw` in ClickHouse. Same shape back.

Try it by hand before trusting the validator:

```bash
uv run python baseline.py
uv run python tests/validate.py
```

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

**Correctness is the gate.** It calls both `pg_answer()` and `ch_answer()`
against the live stack and checks, for BOTH results independently, that
every category's count matches `data/ground-truth.json`'s
`per_category_instock` exactly, every category's avg_price matches within
0.01, and the category set matches exactly (no engine missing or
inventing a category). A fast wrong answer fails -- this is checked before
timing is even considered.

**Timing is recorded, not gated.** The validator times both functions with
`time_it`, refreshes `baseline-local.json`, and prints `pg_seconds`,
`ch_seconds`, and the ratio between them. This is informational: at the
light scale used for local verification (hundreds of thousands of rows),
per-query connection and HTTP overhead can dominate the actual aggregation
work, so ClickHouse does not reliably beat Postgres on wall clock at that
size -- the validator does not assert a winner. The interesting comparison
is qualitative (look at `EXPLAIN` / the query plan on each side -- see
"Topics" below) and becomes a real wall-clock story once you're at tens of
millions of rows. Per repo convention, any timing assertion is always
*relative* to a same-machine baseline, never an absolute threshold.

Fails cleanly (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack
is down, either function still raises `NotImplementedError`, or either
engine's result disagrees with ground truth.

## Estimated evenings

1

## Topics to read up on

- Row store vs columnar storage: why a row store must visit every column
  of every row it reads, while a columnar engine reads only the columns
  the query touches
- Why an unindexed `GROUP BY` over a filtered predicate forces Postgres
  into a full sequential scan of the heap -- run `EXPLAIN ANALYZE` on your
  `pg_answer()` query and read the plan: look for `Seq Scan`, the rows
  estimate vs actual, and where the filter is applied
- ClickHouse column pruning: a `MergeTree` query that only touches
  `category`, `in_stock`, and `price` never reads the other columns off
  disk at all
- Vectorized aggregation: how ClickHouse processes columns in batches
  instead of row-by-row, and why that matters for a `GROUP BY` + `avg()`
  over millions of rows
- Why this repo always benchmarks with a relative, same-machine baseline
  instead of an absolute time threshold

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, ground-truth internals, and design rationale for every task in this
module -- spoilers. Don't read it before finishing this task.
