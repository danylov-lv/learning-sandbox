# Hint 3 -- concrete shape

`src/build.py`:

- `create_rollup`: `DROP VIEW/TABLE IF EXISTS` the view, then the target,
  then the landing table, in that order. `t09_landing` -- plain
  `MergeTree`, the 8 `observations_raw` columns, `ORDER BY (category,
  scraped_at)`. `t09_daily_category` -- `day Date`, `category
  LowCardinality(String)`, a count column, a price_sum column, `ORDER BY
  (day, category)`, engine `SummingMergeTree` (simplest: plain sums) or
  `AggregatingMergeTree` (needs `-State`/`-Merge`). `t09_daily_category_mv`
  -- `CREATE MATERIALIZED VIEW t09_daily_category_mv TO t09_daily_category
  AS SELECT toDate(scraped_at) AS day, category, count() AS <count col>,
  sum(price) AS <sum col> FROM t09_landing GROUP BY day, category`. No
  `POPULATE`.
- `rollup_query`: a string, `SELECT day, category, sum(<count col>),
  sum(<sum col>) FROM t09_daily_category GROUP BY day, category` (swap
  `sum()` for the matching `-Merge()` if you went `AggregatingMergeTree`).
- `total_price_sum`: one query, `SELECT sum(price) FROM observations_raw`,
  return `float(rows[0][0])`.
- `per_category_instock`: `SELECT category, count(), avg(price) FROM
  observations_raw WHERE in_stock GROUP BY category`, build a dict from the
  rows: `{category: (int(count), float(avg))}`.
- `top_sellers`: `SELECT seller_id, count() AS c FROM observations_raw GROUP
  BY seller_id ORDER BY c DESC, seller_id ASC LIMIT 10`, return
  `[[int(sid), int(c)] for sid, c in rows]`.

`src/lake_check.py` -- same four query shapes as above, but every `FROM
observations_raw` becomes `FROM read_parquet('<glob>',
hive_partitioning=true)` with `<glob>` from `parquet_glob()`, and
`one_category_files` adds `filename=true` to that `read_parquet(...)` call
plus `WHERE category = '<category>'`, `SELECT DISTINCT filename`.

`DESIGN.md` -- write each section as 3-6 sentences citing an actual number
or observation: the exact `ORDER BY` tuples you used, whether `FINAL` or
`GROUP BY`/`-Merge` felt cheaper for reading the rollup back, what the CP1
vs CP2 agreement actually proves (and doesn't), and one concrete change
you'd make to the schema or the pipeline at 50M/500M rows (e.g. does
`t09_landing`'s single `ORDER BY (category, scraped_at)` still make sense,
does the rollup table need partitioning by month, would you keep streaming
through a landing table at all versus a different ingestion path).
