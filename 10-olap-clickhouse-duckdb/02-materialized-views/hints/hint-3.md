# Hint 3 -- concrete approach

Work through `create_pipeline(client)` in exactly this order, each step a
separate `client.command(...)`:

1. Drop, in dependency order: the view first, then the target, then the
   landing table. `DROP VIEW IF EXISTS` / `DROP TABLE IF EXISTS` for each --
   this is what makes the function safe to call twice.
2. Create the landing table: `MergeTree`, the 8 `observations_raw` columns
   verbatim, `ORDER BY (category, scraped_at)`.
3. Create the target table with two columns beyond `day Date` and `category
   LowCardinality(String)`: one for the running count, one for the running
   price sum. `ORDER BY (day, category)`. Engine `SummingMergeTree` (no
   extra arguments needed when every non-key column should be summed) or
   `AggregatingMergeTree` if you went the `AggregateFunction` route.
4. Create the view with `CREATE MATERIALIZED VIEW <name> TO <target> AS
   SELECT ...` -- note `TO <target>`, not a bare `CREATE MATERIALIZED VIEW
   <name> AS SELECT ...` (the latter creates its own implicit inner table
   instead of feeding the one you already made). The `SELECT` reads `FROM
   t02_landing`, projects `toDate(scraped_at) AS day`, `category`, an
   aggregate for the count (`count()` or `countState()`), an aggregate for
   the price sum (`sum(price)` or `sumState(price)`), and ends with `GROUP
   BY day, category`.

For `final_rollup_query()`, return a single string: `SELECT day, category,
<collapse-count>, <collapse-price_sum> FROM t02_daily_category GROUP BY day,
category`, where `<collapse-count>` is `sum(count_column)` for
`SummingMergeTree` or `countMerge(count_column)` for `AggregatingMergeTree`
(same idea for the price sum column). Give the two output columns names
your validator-facing contract expects: `count` and `price_sum`, in that
column order after `day, category`.

Sanity-check it yourself before running the validator: after
`create_pipeline`, insert two or three separate batches into `t02_landing`
(anything -- a `WHERE` slice of `observations_raw` works) and run `SELECT
count() FROM t02_daily_category` raw, with no `GROUP BY`. If your view and
engine are wired correctly, that raw count should be noticeably *larger*
than the number of distinct (day, category) pairs you inserted -- that gap
is the partials your `final_rollup_query()` needs to fold back down to one
row per key.
