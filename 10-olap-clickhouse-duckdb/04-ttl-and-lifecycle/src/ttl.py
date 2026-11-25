"""s09.t04 -- table TTL and why it only fires on merge.

A ClickHouse `TTL` clause is not a background daemon that sweeps rows away
on a timer, and it is not checked when you run a SELECT. It is evaluated as
part of a MERGE -- the same background process that combines small parts
into bigger ones. When a merge considers a part, it checks each row's TTL
expression against `now()` at THAT moment, and drops any row for which the
expression says "expired". Insert a fresh batch of rows into a table with a
TTL and query it a second later: nothing has merged yet, so nothing has been
checked, so every row is still there -- regardless of how old `scraped_at`
is. That is not a bug; it is exactly how TTL is documented to behave. It
means a short script that inserts data and expects expired rows to be gone
immediately has to explicitly force the check, rather than wait for it.

You implement four functions:

  1. `create_table_with_ttl(client)` -- create the TTL-bearing table
     (idempotent).
  2. `load_from_raw(client)` -- copy all of `observations_raw` into it.
  3. `force_ttl(client)` -- make ClickHouse apply the TTL against the
     current parts RIGHT NOW, instead of waiting for a background merge.
  4. `surviving_count_query()` / `oldest_surviving_query()` -- SQL strings
     the validator executes to check what actually survived.

Try it by hand before trusting the validator:

    uv run python -c "
    from harness.common import ch_client, ch_query
    import sys; sys.path.insert(0, 'src')
    import ttl
    c = ch_client()
    ttl.create_table_with_ttl(c)
    ttl.load_from_raw(c)
    print('before force_ttl:', ch_query(ttl.surviving_count_query(), client=c))
    ttl.force_ttl(c)
    print('after force_ttl:', ch_query(ttl.surviving_count_query(), client=c))
    print('oldest surviving:', ch_query(ttl.oldest_surviving_query(), client=c))
    "

    uv run python tests/validate.py
"""

TABLE = "t04_observations_ttl"

# Fixed by the README: rows older than this, relative to now() at the
# moment the TTL is applied, are deleted. Keep this literal in the SQL you
# build below -- the validator derives its own expected answer against
# ClickHouse independently, using the same interval.
RETENTION = "INTERVAL 15 MONTH"


def create_table_with_ttl(client) -> None:
    """Create `price_history.t04_observations_ttl` with a table-level TTL.

    `client` is a live clickhouse-connect client on the `price_history`
    database (given -- see harness `ch_client()`).

    Must be IDEMPOTENT: `DROP TABLE IF EXISTS t04_observations_ttl` first,
    then create it fresh, so repeated validator runs never fail on "table
    already exists" and never inherit rows (or a stale TTL) from a
    previous run.

    Columns: the SAME 8 columns as `observations_raw`, same types and same
    order --

        observation_id UInt64
        product_id     UInt32
        seller_id      UInt32
        category       LowCardinality(String)
        currency       LowCardinality(String)
        price          Float64
        in_stock       UInt8
        scraped_at     DateTime

    Engine: `MergeTree`, `ORDER BY (category, product_id, scraped_at)` --
    same ordering as `observations_raw`, so this task is purely about TTL,
    not a different indexing story.

    TTL: a table-level clause, `TTL scraped_at + INTERVAL 15 MONTH DELETE`.
    Read that as "this row's expiry timestamp is `scraped_at` plus 15
    months; once `now()` passes that timestamp, DELETE the row on the next
    merge that considers it". The `RETENTION` constant above spells out the
    interval; use it (or the literal `INTERVAL 15 MONTH`) verbatim -- this
    number is fixed by the README, not something to tune.

    A `TTL` clause is written as part of the `CREATE TABLE` statement,
    after the `ORDER BY`. Use `client.command(...)` for both the DROP and
    the CREATE (no result set expected from either).
    """
    raise NotImplementedError


def load_from_raw(client) -> None:
    """Land the entire corpus into `t04_observations_ttl`, unfiltered.

    `client` is the live clickhouse-connect client. A single `INSERT INTO
    t04_observations_ttl SELECT * FROM observations_raw` (via
    `client.command(...)`) copies all rows across, columns 1:1 since both
    tables share the same 8-column shape.

    Do not filter anything out yourself here -- every row, including ones
    already older than 15 months by wall-clock time, must land in the
    table first. The TTL deleting them is ClickHouse's job, exercised by
    `force_ttl`, not something you pre-filter in this INSERT. Immediately
    after this call, the table should still hold every row you just
    inserted: nothing has merged yet, so nothing has been checked against
    the TTL.
    """
    raise NotImplementedError


def force_ttl(client) -> None:
    """Force ClickHouse to apply the table's TTL against its CURRENT parts,
    right now, instead of waiting for a background merge that might not run
    for a while (or, in a short-lived script, might never run at all before
    the process exits).

    `client` is the live clickhouse-connect client. There are two documented
    ways to force this; either is acceptable here:

      * `OPTIMIZE TABLE t04_observations_ttl FINAL` -- forces ClickHouse to
        merge all of the table's current parts into one. TTL expiry
        checking happens as part of that merge, so any row whose TTL
        expression has passed gets dropped as a side effect of the merge
        completing.
      * `ALTER TABLE t04_observations_ttl MATERIALIZE TTL` -- more directly
        named for this purpose: it tells ClickHouse to recalculate and
        apply TTL expressions for existing parts explicitly, without you
        having to reach for a general-purpose merge command to get there.

    Whichever you choose, this call must block until the deletion has
    actually happened -- `client.command(...)` on either statement waits
    for the operation to finish before returning, which is what makes the
    very next SELECT in this task's flow see the post-TTL state
    deterministically, rather than racing a background process.
    """
    raise NotImplementedError


def surviving_count_query() -> str:
    """Return a SQL string: `count()` over `t04_observations_ttl`, exactly
    as it stands right now -- no WHERE clause, no filtering in Python. This
    is what "how many rows survived the TTL" means: whatever the table
    currently holds. The returned string is executed as-is by the validator
    (e.g. via harness `ch_query(sql, client=client)`), so it must be a
    complete, self-contained SELECT returning a single row with a single
    count column.
    """
    raise NotImplementedError


def oldest_surviving_query() -> str:
    """Return a SQL string: `min(scraped_at)` over `t04_observations_ttl`,
    as it stands right now. After `force_ttl` has run, this tells you the
    OLDEST row that survived -- the validator's proof that nothing older
    than the 15-month cutoff slipped through. Self-contained SELECT
    returning a single row with a single timestamp column, same rules as
    `surviving_count_query()`.
    """
    raise NotImplementedError
