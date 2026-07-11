# 01 -- MergeTree and the Primary Index

## Backstory

You've got 500k (and eventually 50M) scraped price observations sitting in
ClickHouse's `price_history.observations_raw`. Two kinds of questions come
up constantly against a table like this: "what's the average in-stock price
per category, across everything" (touches most of the table, no way around
it), and "show me this one product's price history" (touches a handful of
rows out of hundreds of thousands of products). A row store answers both by
scanning or by maintaining secondary indexes. ClickHouse's MergeTree engine
does something different: it doesn't have a separate B-tree index sitting
next to the data -- the `ORDER BY` clause on the table **is** the index. Data
is physically stored on disk sorted by that tuple, and a sparse index (one
entry per 8192-row granule, not one per row) lets ClickHouse binary-search
straight to the granules that could possibly contain what you're asking for,
skipping the rest without reading them.

The table under study:

```sql
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
```

`category` leads because the per-category analytical queries are this
table's bread and butter and there are only 8 distinct categories.
`product_id` comes second so "one product's history" queries prune within a
category. `scraped_at` trails, giving time-range locality once you're
already down to one product. This task is about seeing that structure pay
off -- and about noticing where it doesn't.

## What's given

- `src/queries.py` -- four functions, each returning a ClickHouse SQL
  string. Rich docstrings on each explain exactly what to query and what
  shape to return. All four currently `raise NotImplementedError`.
- The live stack: ClickHouse HTTP on `localhost:8309`, DB `price_history`,
  user/password `sandbox`/`sandbox`. `harness/common.py` gives you
  `ch_client()`, `ch_query()`, and -- the one that matters most here --
  `ch_read_rows()`, which runs a query and reports exactly how many rows
  ClickHouse read off disk to answer it (via `system.query_log.read_rows`),
  not how many rows it returned.
- `data/ground-truth.json`, the committed answer key (see the module
  README for how it's kept coherent with whatever scale the stack is
  currently loaded at).

## What's required

Implement all four functions in `src/queries.py`:

1. **`category_instock_agg()`** -- per-category `(category, count,
   avg(price))` over `in_stock = 1` rows. Must be correct: the validator
   checks every category's count exactly and its average within a small
   tolerance against ground truth's `per_category_instock`. This one is not
   about pruning (`in_stock` isn't a leading ORDER BY column) -- it's the
   correctness gate you have to clear before the pruning checks even run.
2. **`one_product_history(category, product_id)`** -- `(scraped_at, price)`
   for one product within its category, in time order. The filter
   constrains the first two ORDER BY columns with equality, so this should
   prune down to a handful of granules regardless of how large the table
   gets.
3. **`full_scan_sum()`** -- `sum(price)` over the whole table, no prunable
   predicate. The full-scan baseline. (Not `count(*)` -- see "topics to
   read up on" below for why that would be a useless baseline here.)
4. **`pruned_sum(category, max_product_id)`** -- `sum(price)` filtered by
   `category = <c> AND product_id < <n>`, aligned with the ORDER BY prefix.

Try your queries by hand before trusting the validator -- open a client
(`uv run python -c "from harness.common import ch_client; ..."` or any
ClickHouse client you like against port 8309) and just run the SQL your
functions produce; look at the row counts and results before you look at
`read_rows`.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Runs `category_instock_agg()` and checks every category's count (exact)
  and average price (within 0.01) against
  `data/ground-truth.json`'s `per_category_instock`.
- Runs `full_scan_sum()` and `pruned_sum("electronics", 50)` through
  `ch_read_rows()` and asserts the pruned query reads strictly fewer rows
  than the full scan, AND that it reads under 10% of the table's total row
  count -- a fast wrong answer, or a pruned query that barely prunes, both
  fail this.
- Finds one real `(category, product_id)` pair live from the table, runs
  `one_product_history()` against it, and asserts its `read_rows` is far
  below the full-scan figure.
- Prints a `PASSED` message with the actual read_rows numbers observed on
  this run, or `NOT PASSED: <reason>` and exits 1 on any failure --
  including the stack being down, a function still raising
  `NotImplementedError`, or a wrong answer.

## Estimated evenings

1

## Topics to read up on

- MergeTree's sparse primary index: how `ORDER BY` becomes the index, and
  why it's "sparse" (one mark per granule, not per row)
- Granules and `index_granularity` (default 8192 rows) -- the unit
  ClickHouse can skip or must read
- Part pruning vs granule pruning, and why a leading-prefix WHERE is what
  makes either possible (and why a filter on a non-leading, or non-prefix,
  column can't use the index the same way)
- `system.query_log` and its `read_rows` column -- what it does and doesn't
  measure
- Why `SELECT count()` in ClickHouse can be answered from part metadata
  alone and reads ~0 rows, making it a useless proxy for "how much did this
  query actually scan"
- `LowCardinality(String)` -- what it does to storage and to filtering on
  `category`

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and design rationale for every task in this module -- spoilers.
Don't read it before finishing this task.
