"""s09.t02 -- materialized views as incremental streaming aggregation.

A ClickHouse MATERIALIZED VIEW is not a cached query you refresh on a
schedule. It is an INSERT TRIGGER: it is defined as a SELECT over a source
table, and every time a block of rows lands in that source table (via any
INSERT), the view's SELECT runs over just that new block and the result is
appended into a target table. It never looks at rows that already existed in
the source before the view was created, and it never re-scans the source
later -- there is no "refresh".

That has a consequence you have to design around: if you pointed a
materialized view at `observations_raw` right now, it would fire on the NEXT
insert into that table and would never see the 500k rows already sitting in
it. To demonstrate (and exercise) incremental maintenance honestly, this task
uses a fresh, empty LANDING table (`t02_landing`) as the view's source. The
validator streams the existing corpus into `t02_landing` in several batches
-- simulating a scraper's ongoing inserts -- and your view must maintain a
running per-(day, category) rollup in a TARGET table as each batch arrives.

The rollup being maintained matches ground truth's `daily_category`: for
every (day, category) pair, the observation `count` and the `price_sum`.

You will implement two functions:

  * `create_pipeline(client)` -- creates the landing table, the target table,
    and the materialized view that connects them. Must be idempotent (safe
    to call against a database that already has a previous run's t02_*
    objects sitting in it).
  * `final_rollup_query()` -- returns the SQL that reads the CORRECT, fully
    collapsed answer back out of the target table.

All object names are prefixed `t02_` so this task's objects can't collide
with anything else in the `price_history` database.

Try it by hand before trusting the validator:

    uv run python tests/validate.py
"""

LANDING_TABLE = "t02_landing"
TARGET_TABLE = "t02_daily_category"
MV_NAME = "t02_daily_category_mv"


def create_pipeline(client):
    """Create the landing table, the target rollup table, and the
    materialized view that keeps the target incrementally up to date as rows
    are inserted into the landing table.

    `client` is a live clickhouse-connect client on the `price_history`
    database (given -- see tests/validate.py, which opens it via harness
    `ch_client()`). Use `client.command(...)` for each DDL statement (or the
    harness `ch_command(...)` helper).

    Must be idempotent: DROP IF EXISTS the view, the target table, and the
    landing table (in that order -- the view references the other two) before
    creating anything, so this function can be called repeatedly against a
    database that still has a previous run's objects in it.

    1. `t02_landing` -- a MergeTree with the SAME 8 columns as
       `observations_raw` (`observation_id UInt64`, `product_id UInt32`,
       `seller_id UInt32`, `category LowCardinality(String)`,
       `currency LowCardinality(String)`, `price Float64`,
       `in_stock UInt8`, `scraped_at DateTime`), `ORDER BY (category,
       scraped_at)`. This table stays otherwise empty at rest -- it exists
       only so something can INSERT into it and trip the materialized view.
       (Nothing here reads FROM observations_raw directly -- that table is
       given, already 500k rows, and a materialized view would never see
       rows already sitting in a table when the view is created.)

    2. `t02_daily_category` -- the target rollup table, one row per (day,
       category) key at rest. Needs a `day Date` column, a `category
       LowCardinality(String)` column, and columns to hold the running
       `count` and `price_sum`. Pick an engine that can incrementally
       combine multiple partial rows for the SAME (day, category) key
       written by different insert batches:

         - `SummingMergeTree` sums numeric columns not part of the ORDER BY
           key across rows sharing that key, once ClickHouse gets around to
           merging the parts. Simple, and a natural fit when every column
           you're maintaining is a plain sum (count is just `sum(1)`).
         - `AggregatingMergeTree` stores `AggregateFunction(...)` states
           (written via `-State` combinators, e.g. `sumState`, `countState`)
           and merges those states on merge; reading them back out requires
           the matching `-Merge` combinator. More general (needed for things
           like `avg` or `uniq` that aren't a simple sum of parts), more
           ceremony.

       Either is a legitimate choice for this task since count and price_sum
       are both plain additive aggregates. `ORDER BY (day, category)` (this
       doubles as the MergeTree key that same-key rows collapse on).

    3. `t02_daily_category_mv` -- a MATERIALIZED VIEW whose source is
       `t02_landing` and whose destination is `t02_daily_category` (`CREATE
       MATERIALIZED VIEW ... TO <target> AS SELECT ... FROM t02_landing
       GROUP BY day, category`). The SELECT computes, per block of newly
       inserted rows: `day` (from `scraped_at`, truncated to a date),
       `category`, the count of rows, and the sum of `price` -- shaped to
       match whichever engine/columns you picked for the target (plain
       aggregates for `SummingMergeTree`, `-State` aggregates for
       `AggregatingMergeTree`). Remember this view only ever sees the rows in
       the block that was just inserted into `t02_landing`, not the whole
       table -- which is exactly why the GROUP BY in the view's SELECT
       produces one PARTIAL row per (day, category) key touched by that
       block, and why the target table needs an engine that knows how to
       combine those partials with the ones from every other block.

    Nothing here should use `POPULATE`. `POPULATE` would backfill the view
    from whatever is already in `t02_landing` at creation time, which is
    always empty right after the DROP/CREATE above -- and more importantly,
    `POPULATE` races any concurrent insert into the source during its
    backfill window, silently double-counting or dropping rows. This task is
    specifically about the view firing on each subsequent INSERT, not about
    a one-shot backfill.
    """
    raise NotImplementedError


def final_rollup_query() -> str:
    """Return a SQL string that reads the target table (`t02_daily_category`)
    and produces the FINAL, fully collapsed per-(day, category) rollup: one
    row per key, with columns `(day, category, count, price_sum)`.

    Why this can't be a bare `SELECT * FROM t02_daily_category`: the
    materialized view appends one PARTIAL row per (day, category) key EVERY
    time a block lands in `t02_landing`. ClickHouse merges parts (and
    collapses same-key partials) as a background process on its own
    schedule -- it is not guaranteed to have happened by the time you query,
    especially right after a burst of inserts. So the query itself has to do
    the collapsing:

      - If the target is `SummingMergeTree`: `GROUP BY day, category` with
        `sum(count)` / `sum(price_sum)` (using whatever you named the
        count/sum columns) folds every partial row for a key into one,
        regardless of whether a background merge has run yet.
      - If the target is `AggregatingMergeTree`: apply the matching `-Merge`
        combinator (e.g. `countMerge`, `sumMerge`) to each `AggregateFunction`
        column, again with `GROUP BY day, category`, for the same reason.

    `FINAL` (as a table modifier) is the other way to force ClickHouse to
    merge parts at query time instead of relying on the background merge --
    but it does not, by itself, collapse an `AggregateFunction` column into a
    plain value; you'd still need the `-Merge` combinator on top of it. The
    `GROUP BY ... sum()/​-Merge()` approach above is correct with or without
    parts having merged yet, so it's the one to reach for here.

    The returned string is executed as-is by the validator (e.g. via the
    harness `ch_query(sql, client=client)`), so it must be a complete,
    self-contained SELECT. `price_sum` will be compared to ground truth with
    a small rounding tolerance (0.01) -- you do not need to round it in SQL.
    """
    raise NotImplementedError
