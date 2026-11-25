# Hint 2 -- narrowing to a mechanism

**CP1, `create_rollup` / `rollup_query`:** three objects, same relationship
as task 02 -- an empty landing table you insert into, a target table whose
engine can combine same-key partial rows written by different insert
batches, and a `MATERIALIZED VIEW ... TO <target> AS SELECT ... FROM
<landing> GROUP BY day, category`. `rollup_query()` has to fold whatever's
in the target down to one row per key itself (`GROUP BY` + `sum()` or the
`-Merge` combinator) -- it cannot assume a background merge already ran.

**CP1, the other three functions:** each is a single `GROUP BY` (or no
`GROUP BY` at all for `total_price_sum`) directly against `observations_raw`
-- no landing table, no view, no state. `top_sellers` needs an explicit
tie-break in the `ORDER BY` (count descending, then `seller_id` ascending)
so the result is deterministic even if two sellers tie, and a `LIMIT`.

**CP2:** every function opens with `read_parquet(parquet_glob(),
hive_partitioning=true)` (import `parquet_glob` from `harness.common`).
`one_category_files` additionally needs `filename=true` on that same
`read_parquet(...)` call so a `filename` column exists to `SELECT DISTINCT`
after filtering `WHERE category = ...` -- filtering on the partition column
itself is what lets DuckDB prune directories instead of opening every
partition's file.

**CP3:** each section of `DESIGN.md` maps to one thing you can point at
concretely: the `ORDER BY` you actually chose for `t09_landing` and
`t09_daily_category` (and `observations_raw`'s own, given to you in the
schema); the cost of the materialized view you maintained in CP1 versus
running `total_price_sum`/`per_category_instock` fresh every time; what
`ReplacingMergeTree`/TTL (tasks 03/04) would need to change if `observations_
raw` itself started receiving corrections or needed to age out; and the
concrete numbers from CP1/CP2 (both matching ground truth, in two different
engines) as the evidence for the ClickHouse-vs-DuckDB section.
