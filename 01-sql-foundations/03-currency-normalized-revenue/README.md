# 03 — Currency-Normalized Revenue

## Backstory

Finance wants a monthly "observed market value" figure per source tier, in
USD, so they can compare it against internal revenue projections. The catalog
is scraped across multiple currencies (EUR, GBP, PLN, USD), and you have a
daily `exchange_rates` table to convert everything to USD. Sounds like a
straightforward join — until you actually run it and the total snapshot count
in your result doesn't add up to the total row count in `price_snapshots`.
Something about how the two tables line up on time is not as simple as it
looks. Figure out what, and fix it, before you hand finance a number that's
quietly missing most of the data.

## What's given

- `price_snapshots(id, product_id, source_id, captured_at, price, currency,
  in_stock)` — `captured_at` is a full timestamp, not just a date.
- `exchange_rates(currency, rate_date, rate_to_usd)` — one row per
  `(currency, date)`, `rate_date` is a date (no time component).
  `amount_in_currency * rate_to_usd = amount_in_usd`.
- `sources(id, name, country, tier, currency)`.

## What's required

One row per (month, source tier), columns in this exact order:

1. `month` — first day of the month (a date), derived from
   `price_snapshots.captured_at`.
2. `tier` — source tier (1, 2, or 3).
3. `snapshot_count` — total number of `price_snapshots` rows in that
   (month, tier) bucket. **Every snapshot must be represented** — this number
   must equal the count of the same rows straight from `price_snapshots`, with
   no rows silently lost in the currency join.
4. `usd_revenue` — sum of each snapshot's `price` converted to USD, rounded
   to 2 decimal places.

Use each snapshot's own `currency` column to pick the right exchange rate row
(a source's declared `currency` and a snapshot's `currency` should agree, but
convert using the snapshot's value). The data spans 18 months and 3 tiers, so
expect 54 output rows.

Before you trust your query, sanity-check it: sum your `snapshot_count`
column across all 54 rows and compare it against `SELECT COUNT(*) FROM
price_snapshots`. If it's off by more than a handful of rows, your join
strategy is dropping data — go find out why before you tune anything else.

## Completion criteria

Run `uv run python validate.py 03` from the module root. It must print
`PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- Temporal joins / "as-of" joins (matching each event to the most recent
  reference value at or before its timestamp)
- LATERAL joins in PostgreSQL
- The difference between a `DATE` and a `TIMESTAMP` column and how implicit
  casts between them behave in a join condition
- Window functions as an alternative way to express "most recent row at or
  before X" (e.g. `DISTINCT ON`)
