"""s09.t01 -- the MergeTree ORDER BY as a sparse primary index.

`price_history.observations_raw` is:

    CREATE TABLE observations_raw (
        observation_id UInt64,
        product_id     UInt32,
        seller_id      UInt32,
        category       LowCardinality(String),
        currency       LowCardinality(String),
        price          Float64,
        in_stock       UInt8,
        scraped_at     DateTime
    )
    ENGINE = MergeTree
    ORDER BY (category, product_id, scraped_at)

In a MergeTree, `ORDER BY` is not just a sort order applied after the fact --
it IS the table's primary index. Data on disk is physically sorted by this
tuple, and ClickHouse stores one sparse index mark per granule (8192 rows by
default), recording the first row's key values in that granule. A WHERE
clause that constrains a LEADING PREFIX of the ORDER BY tuple lets ClickHouse
binary-search the index and skip whole granules (and whole parts) instead of
reading every row. A WHERE clause that does NOT touch a leading prefix (or
that only touches a column deeper in the tuple, e.g. `scraped_at` alone)
cannot prune this way -- every granule might contain a matching row, so
every granule must be read.

The four functions below each return a ClickHouse SQL string (no trailing
semicolon needed). None of them execute anything -- the validator hands the
string to a live clickhouse-connect client. Write real SQL against
`observations_raw`; do not invent a different table name.
"""


def category_instock_agg() -> str:
    """SQL: per-category (category, count, avg(price)) over in_stock=1 rows.

    Query `price_history.observations_raw`. Filter to `in_stock = 1`, group
    by `category`, and select three columns in this order:

        category, count(*) as n, avg(price) as avg_price

    One row per category (8 rows total in the seeded corpus). This must be
    CORRECT -- the validator compares every category's count (exact) and
    avg_price (within a small rounding tolerance) against
    `data/ground-truth.json`'s `per_category_instock`, which was computed
    independently in numpy. Compute the average in ClickHouse; do not pull
    raw rows into Python and average them yourself.

    This query is not the pruning demonstration -- `in_stock` is not a
    leading prefix of the ORDER BY, so it reads (close to) every row. It
    exists purely to prove your SQL is correct before the pruning checks
    run.
    """
    raise NotImplementedError


def one_product_history(category: str, product_id: int) -> str:
    """SQL: (scraped_at, price) for ONE product within its category, in time
    order.

    Query `observations_raw` WHERE `category = <category>` AND `product_id =
    <product_id>`, ordered by `scraped_at`. Select exactly two columns, in
    this order: `scraped_at, price`.

    `category` and `product_id` are the first TWO components of the table's
    ORDER BY -- an equality filter on both is a filter on a leading prefix,
    so ClickHouse's sparse index can jump straight to the handful of
    granules that can possibly contain this product's rows and skip
    everything else. That's what makes "one product's price history" cheap
    even though the table has hundreds of thousands of distinct products.

    `category` is a plain Python str (e.g. "electronics") and `product_id`
    is a plain Python int. You may interpolate them into the SQL string
    directly (there's no untrusted input here -- the validator supplies
    both), or build the string however you like, as long as the result is
    valid ClickHouse SQL. Quote the category as a string literal.
    """
    raise NotImplementedError


def full_scan_sum() -> str:
    """SQL: `sum(price)` over the ENTIRE table, no prunable predicate.

    This is the full-scan baseline the pruning proof is measured against.
    Select a single aggregate, `sum(price)`, from `observations_raw`, with
    no WHERE clause (or a WHERE clause that could not possibly let the
    primary index skip any granule -- simplest is to just omit WHERE
    entirely).

    Why `sum(price)` and not `count(*)`: ClickHouse can answer `count(*)`
    from part/granule metadata alone without touching the `price` column's
    data at all, so it reads ~0 rows regardless of pruning -- it would be a
    useless baseline here. `sum(price)` forces ClickHouse to actually read
    the `price` column off disk for every granule it visits, which is what
    makes the read_rows count meaningful.
    """
    raise NotImplementedError


def pruned_sum(category: str, max_product_id: int) -> str:
    """SQL: `sum(price)` filtered by `category = <category> AND product_id <
    <max_product_id>`, aligned with the ORDER BY prefix so it prunes hard.

    Select `sum(price)` from `observations_raw` WHERE `category =
    <category>` AND `product_id < <max_product_id>`. Both predicates
    constrain a leading prefix of `ORDER BY (category, product_id,
    scraped_at)` (an equality on `category`, then a range on `product_id`),
    so ClickHouse's sparse index can skip granules whose index mark proves
    they hold no matching rows -- most of the table, if `max_product_id` is
    small relative to the number of distinct products in that category.

    `category` is a plain Python str, `max_product_id` a plain Python int.
    The validator asserts `ch_read_rows` on this query's output is far
    smaller than `ch_read_rows(full_scan_sum())` -- that gap IS the proof
    the sparse primary index pruned granules instead of scanning the table.
    """
    raise NotImplementedError
