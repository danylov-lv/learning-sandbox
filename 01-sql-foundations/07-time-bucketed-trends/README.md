# 07 — Time-Bucketed Trends

## Backstory

The sales team asked for a weekly trend chart: "how many prices are we tracking, and
what's the average USD price, week over week." The first version of this query grouped
by `date_trunc('week', captured_at)` and counted rows. It shipped, and within a day
someone noticed two problems: the "distinct products tracked" number was actually
counting rows, not products — so a product scraped by five sources counted as five —
and weeks with sparse scraping activity (a scraper outage, a holiday) showed phantom
price dips because the row count for that week collapsed and skewed the average toward
whichever sources happened to still be reporting.

You're asked to rebuild the query so the sales team can trust it: separate "how much
data did we collect" from "how many distinct things did we observe" from "what's the
actual price signal," all broken out by source tier so a dip in tier-3 (long-tail)
scraping doesn't get mistaken for a market-wide price move.

## What's given

- `price_snapshots(id, product_id, source_id, captured_at, price, currency, in_stock)`
- `sources(id, name, country, tier, currency)` — `tier` is smallint (1 = major
  marketplace, 2 = mid, 3 = long tail).
- Full data range: 2025-01-01 through 2026-06-30 (78 full ISO weeks plus a partial
  week at each end — 79 distinct week buckets total).

## What's required

One row per (ISO week start date, tier), covering the full data range, with columns
in this exact order:

- `week_start` — the Monday that starts the ISO week (`date_trunc('week', captured_at)`
  cast to `date`).
- `tier` — the source's tier.
- `snapshot_count` — total number of `price_snapshots` rows in that (week, tier)
  bucket. This is "how much data did we collect," and it is expected to be noisy —
  do not try to smooth it.
- `distinct_products` — count of **distinct** `product_id` values in the bucket. This
  is the number that was wrong in the original query.
- `distinct_product_source_pairs` — count of distinct `(product_id, source_id)`
  combinations in the bucket. This sits between the two: it tells you how much
  scraping coverage you had, independent of how many snapshots each pair produced.
- `avg_price_usd` — average `price` for snapshots where `currency = 'USD'` only,
  rounded to 2 decimal places. Do not attempt currency conversion here — that is the
  subject of a later, harder task. Restricting to USD-native sources keeps the number
  honest without needing exchange rates.

Group by the untruncated week boundary (not a formatted string) and by tier. Order does
not matter — the validator sorts canonically.

## Completion criteria

Write your query into `src/query.sql`. From the module root:

```
uv run python validate.py 07
```

Must print `PASSED`.

## Estimated evenings

1

## Topics to read up on

- `date_trunc` and truncation granularities
- ISO week semantics (which day a week starts on, partial boundary weeks)
- `COUNT(DISTINCT ...)` vs `COUNT(*)` and when each is correct
- `FILTER (WHERE ...)` clause on aggregates vs a `WHERE` clause on the query
- Why grouping by a formatted/string date bucket instead of the truncated timestamp
  can silently break sort order and joins downstream
