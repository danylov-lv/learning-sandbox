# Hint 3

Suggested build order, in `src/star.sql`:

1. `CREATE SCHEMA mart;` then the four `CREATE TABLE` statements. Give
   `dim_shop` and `dim_product` a serial/identity surrogate key, their
   natural key column(s), the descriptive attributes you need, and
   `valid_from timestamptz` / `valid_to timestamptz` (nullable, or a
   sentinel far-future value for the current version — your choice, just
   be consistent). Give `dim_date` a date primary key plus the derived
   columns (year, month as `'YYYY-MM'` text or similar, quarter as
   `'YYYY-Qn'` text) that q09/q11 will group by directly.

2. Populate `dim_date` first with `generate_series` — it has no
   dependency on anything else.

3. Populate `dim_shop` and `dim_product` from your task-02 SCD2 tables:
   `INSERT INTO mart.dim_shop (...) SELECT ... FROM <your scd2 shop
   history table>`. One source row per version, in the same shape.

4. Populate `fact_price_observation` last, from your deduplicated
   observations, with something like (in words, not SQL):
   "for each deduplicated observation, join to `dim_shop` on
   `shop_code` where the observation's `event_time` falls inside that
   dim row's `[valid_from, valid_to)`, do the same for `dim_product`,
   join to `dim_date` on the observation's date, and insert one fact row
   carrying the three surrogate keys plus the USD price." If your task-01
   loader already has a deduplicated observations table/view, start from
   that instead of re-deriving deduplication here.

For q11's ranking: partition by quarter, order by `observation_count`
descending and brand ascending as the tiebreak, and use a window function
that gives contiguous 1..5 ranks (not one that leaves gaps on ties) —
`ROW_NUMBER()` over that exact `ORDER BY` gets you a unique 1..5 per
quarter directly, since the tiebreak on brand already makes the ordering
total. Filter to `rank <= 5` in an outer query, since window functions
can't be filtered in the same `SELECT` they're computed in.
