# Capstone Design Memo -- Analytical Serving Layer for Scraped Price History

Fill in each section with your own analysis, grounded in what you built and
measured across CP1 and CP2 of this capstone, and across tasks 01-08 of this
module.

## ORDER BY / primary index choice

(fill in -- for `t09_landing` and `t09_daily_category`, and for
`observations_raw` itself, what ORDER BY did you use or rely on, why that
column order specifically, and what query shapes it prunes well versus what
it can't help with)

## Rollup: materialized view vs on-demand aggregation

(fill in -- for the per-(day, category) rollup you built in CP1, when is a
standing materialized view worth its maintenance cost versus just running
`total_price_sum` / `per_category_instock` on demand every time, as CP1's
other three functions do; what would make you reach for a materialized view
for THOSE too)

## Latest-state and lifecycle (ReplacingMergeTree / TTL)

(fill in -- this serving layer's `observations_raw` is append-only and
`t09_landing` is a one-shot demo, but a real scraper re-ingests and
eventually wants to age data out; how would ReplacingMergeTree and TTL
(tasks 03/04) fit into this specific serving layer if the scraper started
sending corrections and you needed to drop data older than N days)

## ClickHouse server vs DuckDB for this serving layer

(fill in -- tie this to task 08: given that CP2 proved DuckDB over the
Parquet lake reproduces every aggregate CP1 computed in ClickHouse, under
what concrete conditions would you actually run the ClickHouse server for
this serving layer instead of just pointing DuckDB at the lake; what does
the incremental materialized view in CP1 buy you that a DuckDB-over-Parquet
setup structurally cannot)

## What I'd change at 50M / 500M rows

(fill in -- this capstone ran against a light-scale corpus; what specifically
would you change about the schema, the rollup design, the landing/streaming
approach, or the choice between ClickHouse and DuckDB if this were 50M rows,
and again at 500M)
