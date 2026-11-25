# Hint 3

One concrete way to structure `load.py`, in words:

1. Create a staging table with a single `jsonb` (or `text`) column, one row
   per line of `events.jsonl`. Load it with `COPY ... FROM STDIN` (psycopg
   lets you feed it a Python file object line by line, or the raw bytes
   directly) — this is the part that has to be fast, and `COPY` is the tool
   for it.
2. Populate your entity tables (shops, products) by filtering the staging
   table to the relevant `event_type` values, ordered by `event_time`, and
   taking the first (or folding in order) per entity. These are small
   compared to observations, so plain `INSERT ... SELECT` is fine here.
3. Populate listings similarly from `product_discovered` /
   `product_delisted` / `product_relisted`, tracking the lifecycle so a
   "currently active" flag (or an equivalent derivable column) is directly
   queryable for q01.
4. Populate observations from `price_observed` rows in the staging table,
   extracting fields out of the `jsonb` with `->>`. Deduplicate in the same
   statement: window over `(shop_code, product_code, event_time)` ordered by
   `ingested_at` and keep only the first row per group — `DISTINCT ON` with
   an `ORDER BY` matching that key, or `ROW_NUMBER() OVER (...) = 1` in a
   CTE, both do this in one pass without a second staging round-trip.
5. Drop or truncate the staging table when done, or leave it — your call,
   but document which in the load.py docstring since later tasks assume this
   loader ran once and won't re-run it for you.

For the FX conversion in q02/q04: store the rate table itself (e.g. one small
table `currency, rate_to_usd`), not pre-multiplied USD amounts, so a query
can join to it — this keeps the observation row itself a faithful copy of
what was actually scraped.
