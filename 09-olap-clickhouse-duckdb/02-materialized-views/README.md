# 02 -- Materialized Views

## Backstory

The scraper never stops. Every few minutes another batch of price
observations lands in `observations_raw`. Somewhere downstream, a dashboard
wants "count and total price, per day, per category" -- and it wants that
number to be current, not a nightly batch job that ran eight hours ago. You
could re-run `GROUP BY toDate(scraped_at), category` over the whole fact
table on every page load, but that re-scans everything, every time, forever,
as the table keeps growing. What you actually want is a rollup that updates
itself incrementally as new rows arrive, so reading it back out is always
cheap -- one row per (day, category), always current.

That is what a ClickHouse `MATERIALIZED VIEW` is for, and it is worth being
precise about what it actually is, because the name is misleading if you
come from Postgres. A ClickHouse materialized view is not a cached query you
periodically `REFRESH`. It is an **insert trigger**: you define it as a
`SELECT` over a source table, and every time a block of rows is `INSERT`ed
into that source, the view's `SELECT` runs over exactly that new block and
appends the result into a target table. It fires on inserts. It does not
fire on a schedule, and it does not fire retroactively.

That last part has a sharp edge. If you pointed a materialized view at
`observations_raw` right now, it would never see the 500k rows already
sitting there -- it only sees rows inserted *after* the view exists. To
practice incremental maintenance honestly (not by cheating with a one-shot
backfill), this task gives you a fresh, empty **landing table**
(`t02_landing`) to be the view's source. You build the view against that
landing table, and the validator streams the existing corpus into it across
several separate `INSERT`s -- simulating the scraper's ongoing drip of new
data -- so you can watch the target rollup accumulate one batch at a time.

## What's given

- `src/mv.py` -- a scaffold with rich docstrings and two functions that
  `raise NotImplementedError`:
  - `create_pipeline(client)` -- create the landing table, the target rollup
    table, and the materialized view connecting them.
  - `final_rollup_query()` -- return the SQL that reads a correct, fully
    collapsed answer back out of the target.
- The live stack: ClickHouse at `localhost:8309` (HTTP), database
  `price_history`, table `observations_raw` (the given fact table, already
  loaded, 8 columns -- see `src/mv.py`'s docstring for the exact schema).
  `harness/common.py` for `ch_client()` / `ch_query()` / `ch_command()` /
  `load_ground_truth()`.

## What's required

1. `create_pipeline(client)` must create, idempotently (safe to call again
   against a database still holding a previous run's objects):
   - `t02_landing` -- a plain `MergeTree`, same 8 columns as
     `observations_raw`, empty at rest. Nothing pre-populates it.
   - `t02_daily_category` -- the target table, one row per (day, category)
     key once fully collapsed, holding a running `count` and `price_sum`.
     Pick `SummingMergeTree` or `AggregatingMergeTree` -- either is a
     legitimate fit here, since count and price_sum are both plain additive
     aggregates.
   - `t02_daily_category_mv` -- the `MATERIALIZED VIEW`, source
     `t02_landing`, destination `t02_daily_category`, aggregating per (day,
     category) on each insert.
   - No `POPULATE`. See the docstring for why: it races concurrent inserts,
     and this task is specifically about the trigger-on-insert behavior, not
     a one-shot backfill.
2. `final_rollup_query()` must return SQL that collapses however many
   partial rows accumulated per (day, category) key into exactly one row
   per key -- because ClickHouse merges parts (and folds same-key partials
   together) on its own background schedule, which is not guaranteed to
   have run by the time you query.

Try it by hand before trusting the validator -- open a client, call
`create_pipeline`, insert a batch or two into `t02_landing` yourself, and
look at what lands in `t02_daily_category` before and after you apply
`final_rollup_query()`.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Drops any leftover `t02_*` objects, then calls your `create_pipeline`.
- Confirms `t02_landing`, `t02_daily_category`, and `t02_daily_category_mv`
  all exist, and that the landing table is empty right after creation (no
  `POPULATE`, no pre-existing rows).
- Streams the full `observations_raw` corpus into `t02_landing` across 5
  separate `INSERT`s (split by `product_id` modulo, so every batch touches
  most (day, category) keys) -- proving the view accumulates the SAME keys
  across multiple inserts, not just a single one-shot copy.
- Runs your `final_rollup_query()` and compares the collapsed
  `(day, category) -> (count, price_sum)` result to
  `data/ground-truth.json`'s `daily_category`: the **set of keys** must
  match exactly (no missing or extra day/category cells), `count` must
  match exactly, `price_sum` within 0.01.
- Drops all `t02_*` objects in a `finally`, whether the run passed or
  failed, leaving the database in its original state.

Fails cleanly (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack is
down, either function is still `NotImplementedError`, an expected object
wasn't created, the landing table wasn't empty right after
`create_pipeline`, the key set doesn't match ground truth exactly, or any
count/price_sum is off.

## Estimated evenings

1

## Topics to read up on

- Materialized views as insert triggers: fires on `INSERT` into the source,
  never on a schedule, never retroactively over rows already present
- `SummingMergeTree` vs `AggregatingMergeTree` -- when a plain per-column sum
  is enough, and when you need `AggregateFunction` state (`-State` /
  `-Merge` combinators) instead
- Why a `GROUP BY ... sum()` (or `-Merge` combinator) is needed to read a
  correct answer back out before background merges have collapsed the
  parts -- and what `FINAL` does and doesn't do for you here
- `POPULATE` and why it's the wrong tool for backfilling a view against a
  table that's already receiving concurrent writes

## `.authoring/` is off-limits

`.authoring/` holds this module's full data contract and ground-truth
internals -- spoilers for every task, not just this one. Don't read it until
after you've finished (see the module README for the same note).
