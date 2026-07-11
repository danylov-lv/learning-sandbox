"""s09.t03 -- ReplacingMergeTree: dedup on merge, and why FINAL matters.

Your scraper re-ingests the same (product, seller, scraped_at) observation
more than once -- a retry, a re-run of a backfill, an overlapping schedule.
Each re-ingest carries an increasing `version` and `ingested_at`, and the
LATEST version is the truth for that natural key; older versions are noise
you want gone. `ReplacingMergeTree(version)` is built for exactly this: rows
sharing the same ORDER BY key are collapsed down to one, keeping the row with
the highest `version`, during background merges.

The trap this task is built around: merges are asynchronous and their timing
is NOT deterministic. Immediately after an insert, duplicate rows for the
same key can still be sitting in separate, unmerged parts -- a background
merge might not have run at all yet. A naive `SELECT * FROM
t03_observations_dedup` at that point can return several rows for one key,
or (if a merge DID happen to run) exactly one -- and you cannot tell which
situation you're in just by looking at a table name that says
"ReplacingMergeTree". A read that is correct RIGHT NOW, independent of
whether any merge has run, has to either:

  * append `FINAL` to the query (ClickHouse dedups matching parts on the fly
    at query time, before returning rows), or
  * do the dedup yourself with `argMax(col, version)` per key, grouped by the
    ORDER BY columns (a plain aggation, engine-agnostic, works even on a
    MergeTree without ReplacingMergeTree's semantics at all).

Both are correct; they have different costs (FINAL cost scales with how much
unmerged data still needs collapsing at read time; argMax is a GROUP BY over
every duplicate row). You'll measure the difference yourself in this task's
NOTES.

You implement five functions:

  1. `create_table(client)` -- create the target table (idempotent).
  2. `insert_batch(client, rows)` -- load a batch of (possibly duplicate,
     out-of-order) observation rows.
  3. `deduped_state_query()` -- a SELECT that returns the CURRENT state, one
     row per natural key, correct regardless of merge timing.
  4. `count_before_merge()` / `count_after_dedup()` -- two SELECTs that make
     the collapse visible: raw row count vs. distinct-key count.

Try it by hand before trusting the validator:

    uv run python -c "
    import sys; sys.path.insert(0, '.')
    from harness.common import ch_client
    from generate import build_duplicate_batch
    sys.path.insert(0, '03-replacingmergetree-dedup/src')
    import dedup
    c = ch_client()
    dedup.create_table(c)
    rows = build_duplicate_batch(1, 300)
    dedup.insert_batch(c, rows)
    print(c.query(dedup.count_before_merge()).result_rows)
    print(c.query(dedup.count_after_dedup()).result_rows)
    print(c.query(dedup.deduped_state_query()).result_rows[:5])
    "

    uv run python tests/validate.py
"""

TABLE = "t03_observations_dedup"


def create_table(client) -> None:
    """Create `price_history.t03_observations_dedup` as a ReplacingMergeTree.

    `client` is a live clickhouse-connect client on the `price_history`
    database (given -- see harness `ch_client()`).

    Must be IDEMPOTENT: drop the table first (`DROP TABLE IF EXISTS
    t03_observations_dedup`), then create it fresh, so re-running this
    function (e.g. across repeated validator runs) never fails on "table
    already exists" and never leaves stale rows from a previous run behind.

    Columns, in this order:

        product_id  UInt32
        seller_id   UInt32
        scraped_at  DateTime
        category    LowCardinality(String)
        currency    LowCardinality(String)
        price       Float64
        in_stock    UInt8
        version     UInt64
        ingested_at DateTime

    Engine: `ReplacingMergeTree(version)` -- the argument names the column
    ClickHouse compares to decide which of several rows sharing an ORDER BY
    key survives a merge (highest wins).

    ORDER BY: the natural key this task dedups on --
    `(product_id, seller_id, scraped_at)`. This is deliberate: ORDER BY is
    what ReplacingMergeTree groups by when collapsing duplicates. Rows with
    the same (product_id, seller_id, scraped_at) but different version are
    exactly the "same observation, re-ingested" case this task models; rows
    that differ in any ORDER BY column are different observations and must
    never collapse into each other.

    Use `client.command(...)` for the DDL statements (no result set expected).
    """
    raise NotImplementedError


def insert_batch(client, rows) -> None:
    """Insert `rows` into `t03_observations_dedup`, in the order given.

    `client` is the live clickhouse-connect client. `rows` is a list of dicts
    shaped like `generate.build_duplicate_batch(...)`'s output:

        {"product_id": int, "seller_id": int, "scraped_at": datetime,
         "category": str, "currency": str, "price": float, "in_stock": bool,
         "version": int, "ingested_at": datetime}

    Insert them AS GIVEN -- do not sort, dedup, or reorder in Python. The
    whole point is to reproduce a realistic out-of-order duplicate stream and
    let ClickHouse (not your Python code) be responsible for arriving at the
    correct current state.

    Use `client.insert(table, data, column_names=[...])`. clickhouse-connect
    wants row-oriented data -- a sequence of sequences, each inner sequence
    the values for one row in the SAME order as `column_names` -- not a list
    of dicts. Build that from `rows` yourself, converting each row dict into
    a tuple/list in this exact column order:

        product_id, seller_id, scraped_at, category, currency, price,
        in_stock, version, ingested_at

    `in_stock` is a Python bool in the input dicts but the column is UInt8;
    convert explicitly (e.g. `int(row["in_stock"])`) rather than relying on
    an implicit conversion.

    IMPORTANT ClickHouse gotcha: the session setting `optimize_on_insert`
    defaults to `1`. When it's on, ClickHouse pre-collapses rows that share
    an ORDER BY key WITHIN THE SAME inserted block, as if a merge had
    already happened -- BEFORE the part is even written to disk. If you
    insert this whole out-of-order duplicate stream in one call with that
    default in effect, the table will never show you raw duplicates at all
    (there's nothing left to dedup by the time FINAL/argMax would matter),
    which defeats the entire point of this task. Pass
    `settings={"optimize_on_insert": 0}` to `client.insert(...)` so the raw,
    undeduplicated rows actually land on disk -- exactly like a real
    out-of-order re-ingest would, with no synchronous cleanup at insert time
    and no background merge obligated to run either (a single inserted part
    has nothing else to merge with, so it sits there raw until FINAL/argMax
    reads it, or an explicit `OPTIMIZE TABLE ... FINAL`).
    """
    raise NotImplementedError


def deduped_state_query() -> str:
    """SQL: the CURRENT state, one row per natural key, correct RIGHT NOW.

    Return a ClickHouse SQL string (no trailing semicolon needed) against
    `t03_observations_dedup` that selects exactly these columns, in this
    order:

        product_id, seller_id, scraped_at, price, in_stock, version

    One row per distinct (product_id, seller_id, scraped_at) -- the
    highest-`version` row for that key, with THAT row's price/in_stock.

    The one thing this query must NOT do: assume a background merge has
    already collapsed the duplicates. Immediately after `insert_batch`, the
    table can easily still hold multiple unmerged parts, each with its own
    copy of a duplicated key -- ReplacingMergeTree only removes duplicates
    when parts get merged, and merges are asynchronous background work with
    no guaranteed timing. A plain `SELECT * FROM t03_observations_dedup`
    right after inserting is NOT guaranteed to be deduped and NOT guaranteed
    to pick the highest version if it happens to return one row per key
    anyway (you could get lucky and see only the newest part).

    Two approaches are correct here; pick one:

      * Add `FINAL` after the table name in the FROM clause. This tells
        ClickHouse to perform the merge's collapsing logic at query time,
        on whatever parts currently exist, before returning rows -- so the
        result is correct no matter when (or whether) a real background
        merge has run.
      * Skip ReplacingMergeTree's collapsing semantics entirely and compute
        the same answer with a `GROUP BY (product_id, seller_id,
        scraped_at)` using `argMax(price, version)`, `argMax(in_stock,
        version)`, and `max(version)` -- an aggregation that reads every
        duplicate row and picks the one at the winning version explicitly,
        with no dependency on merge state at all.

    Whichever you pick, write your reasoning about the tradeoff (cost,
    when each is appropriate) into this task's NOTES.md.
    """
    raise NotImplementedError


def count_before_merge() -> str:
    """SQL: raw row count in `t03_observations_dedup`, duplicates INCLUDED.

    Return a ClickHouse SQL string selecting a single count -- every row
    ever inserted, with no FINAL and no dedup logic of any kind. This is the
    "before" number: it must equal exactly how many rows `insert_batch`
    inserted, proving nothing was silently dropped or collapsed at insert
    time (ReplacingMergeTree never rejects or merges rows synchronously on
    INSERT -- collapsing is a merge-time, not insert-time, operation).
    """
    raise NotImplementedError


def count_after_dedup() -> str:
    """SQL: the deduped, distinct-key row count, merge-independent.

    Return a ClickHouse SQL string selecting a single count of DISTINCT
    natural keys (product_id, seller_id, scraped_at) -- the "after" number,
    to put side by side with `count_before_merge()`'s raw count and make the
    collapse visible: fewer distinct keys than raw rows is the proof
    duplicates existed at all.

    Like `deduped_state_query()`, this must not depend on whether a
    background merge has already run -- use `FINAL` or a `COUNT(DISTINCT
    ...)` / GROUP BY approach that reads the raw rows and counts groups,
    not something that trusts an unmerged table to already look deduped.
    """
    raise NotImplementedError
