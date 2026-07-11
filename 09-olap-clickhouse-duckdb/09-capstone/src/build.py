"""s09.capstone CP1 -- the ClickHouse serving layer.

Tasks 01-04 each proved one ClickHouse mechanism in isolation: the sparse
primary index (01), a materialized view accumulating a rollup incrementally
(02), ReplacingMergeTree dedup (03), TTL lifecycle (04). This checkpoint asks
you to stand up the thing those were rehearsals for: a small serving layer
over `observations_raw` that a dashboard could actually query -- a live
incremental rollup, plus the handful of aggregate answers a "how's the
catalog doing" page would ask for on every load.

You implement five functions:

  * `create_rollup(client)` -- landing table + target rollup table +
    materialized view, wired together exactly like task 02's
    `create_pipeline`, but under this task's own `t09_` names so it can't
    collide with anything task 02 left behind (that task also tears down
    after itself, but names are prefixed defensively anyway).
  * `rollup_query()` -- SQL string that reads the target table back out,
    fully collapsed.
  * `total_price_sum(client)` -- the grand total price sum over the WHOLE
    `observations_raw` table (not the rollup -- a direct aggregate).
  * `per_category_instock(client)` -- count + avg(price) per category, over
    `in_stock` rows only, again a direct aggregate over `observations_raw`.
  * `top_sellers(client)` -- the 10 sellers with the most observations,
    descending.

All five are graded against `data/ground-truth.json` by the validator, which
also drives the incremental-insert story: it streams `observations_raw` into
`t09_landing` in several separate batches (not one shot), so your view has
to actually accumulate a rollup across multiple inserts to pass, exactly as
in task 02.

Try it by hand before trusting the validator:

    uv run python tests/validate_cp1.py
"""

LANDING_TABLE = "t09_landing"
TARGET_TABLE = "t09_daily_category"
MV_NAME = "t09_daily_category_mv"


def create_rollup(client) -> None:
    """Create the landing table, the target rollup table, and the
    materialized view that keeps the target incrementally up to date as rows
    land in the landing table.

    `client` is a live clickhouse-connect client on the `price_history`
    database (see harness `ch_client()`). Use `client.command(...)` (or the
    harness `ch_command(...)` helper) for each DDL statement.

    Must be IDEMPOTENT: `DROP VIEW/TABLE IF EXISTS` the view, then the
    target, then the landing table (in that order -- the view references
    the other two), before creating anything, so this function is safe to
    call repeatedly against a database that still has a previous run's
    `t09_*` objects sitting in it.

    1. `t09_landing` -- a MergeTree with the SAME 8 columns as
       `observations_raw` (`observation_id UInt64`, `product_id UInt32`,
       `seller_id UInt32`, `category LowCardinality(String)`,
       `currency LowCardinality(String)`, `price Float64`,
       `in_stock UInt8`, `scraped_at DateTime`), `ORDER BY (category,
       scraped_at)`. It stays empty at rest -- it exists only so something
       can INSERT into it and trip the view. Nothing here reads FROM
       `observations_raw` directly: that table already has 500k rows sitting
       in it, and a materialized view never sees rows already present in its
       source at creation time -- only rows inserted afterward.

    2. `t09_daily_category` -- the target rollup table, one row per (day,
       category) key once fully collapsed. Needs a `day Date` column, a
       `category LowCardinality(String)` column, and columns to hold a
       running `count` and `price_sum`. Pick an engine that can incrementally
       combine multiple partial rows written for the SAME (day, category)
       key by different insert batches -- `SummingMergeTree` (sums plain
       numeric columns not in the ORDER BY across same-key rows once merged)
       or `AggregatingMergeTree` (stores `AggregateFunction` state via
       `-State` combinators, read back with the matching `-Merge`
       combinator). Either is legitimate here since count and price_sum are
       both plain additive aggregates. `ORDER BY (day, category)`.

    3. `t09_daily_category_mv` -- a MATERIALIZED VIEW whose source is
       `t09_landing` and whose destination is `t09_daily_category`
       (`CREATE MATERIALIZED VIEW ... TO <target> AS SELECT ... FROM
       t09_landing GROUP BY day, category`). The SELECT computes, per block
       of newly inserted rows: `day` (from `scraped_at`, truncated to a
       date), `category`, the count of rows, and the sum of `price` --
       shaped to match whichever engine/columns you picked for the target.

    No `POPULATE` -- see task 02 for why (it would race concurrent inserts,
    and here the landing table is empty at creation time anyway, so there'd
    be nothing to backfill from).
    """
    raise NotImplementedError


def rollup_query() -> str:
    """Return a SQL string that reads `t09_daily_category` back out as the
    FINAL, fully collapsed per-(day, category) rollup: one row per key, with
    columns `(day, category, count, price_sum)`.

    Why this can't be a bare `SELECT * FROM t09_daily_category`: the view
    appends one PARTIAL row per (day, category) key on every insert batch
    into `t09_landing`, and ClickHouse only folds same-key partials together
    when it gets around to a background merge -- not guaranteed to have
    happened by the time you query, especially right after a burst of
    inserts. The query itself has to do the collapsing:

      - `SummingMergeTree` target: `GROUP BY day, category` with
        `sum(count)` / `sum(price_sum)` (whatever you named those columns).
      - `AggregatingMergeTree` target: the matching `-Merge` combinator on
        each `AggregateFunction` column, still `GROUP BY day, category`.

    Either is correct with or without a background merge having run yet.
    `FINAL` alone does not collapse an `AggregateFunction` column into a
    plain value -- you'd still need `-Merge` on top of it -- so the
    `GROUP BY ... sum()/-Merge()` shape above is the one to reach for.

    The returned string is executed as-is by the validator (via
    `ch_query(sql, client=client)`), so it must be a complete,
    self-contained SELECT. `price_sum` is compared to ground truth with a
    0.01 tolerance -- no need to round it in SQL.
    """
    raise NotImplementedError


def total_price_sum(client) -> float:
    """The grand total price sum over the ENTIRE `observations_raw` table
    (every row, no filter) -- a direct aggregate, unrelated to the rollup
    above.

    Run a single aggregate query (`sum(price)`) against `observations_raw`
    via `client.query(...)` (or the harness `ch_query(...)`), and return the
    result as a plain Python `float`.

    The validator compares this against `data/ground-truth.json`'s
    `price_sum`, within a small rounding tolerance (0.01).
    """
    raise NotImplementedError


def per_category_instock(client) -> dict:
    """Per-category `(count, avg_price)` over `in_stock` rows, computed
    directly against `observations_raw` -- the same benchmark-query shape
    used throughout this module (see task 05's `per_category_instock`).

    Filter to `in_stock` rows, `GROUP BY category`, and compute `count(*)`
    and `avg(price)` IN THE SQL. Return a plain Python
    `dict {category: (count, avg_price)}`, one entry per category present
    in the `in_stock` rows (8 in the seeded corpus). `count` an int,
    `avg_price` a float.

    The validator compares this against `data/ground-truth.json`'s
    `per_category_instock`: every category's `count` must match exactly,
    `avg` within 0.01, and the category set must match (no missing, no
    extra).
    """
    raise NotImplementedError


def top_sellers(client) -> list:
    """The 10 sellers with the most observations in `observations_raw`,
    descending by count.

    `GROUP BY seller_id`, order by the count descending, and break ties by
    `seller_id` ascending (deterministic -- two sellers with the exact same
    count must still come back in a fixed order). Limit to 10 rows.

    Return a list of `[seller_id, count]` pairs (or 2-tuples -- the
    validator only checks the values, not the exact container type), in that
    order, `seller_id` and `count` both plain Python ints.

    The validator compares this list, in order, against
    `data/ground-truth.json`'s `top_sellers_by_count` (already sorted
    descending the same way).
    """
    raise NotImplementedError
