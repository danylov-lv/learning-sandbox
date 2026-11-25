# 08 — Scrape Coverage

## Backstory

The scraping team reviews an hourly dashboard when a marketplace feed goes quiet.
They need to distinguish an hour when the scraper recorded only out-of-stock
products from an hour when it recorded nothing at all. The dashboard needs a row
for every monitored source and hour so it can show both cases.

## What's given

- `price_snapshots(id, product_id, source_id, captured_at, price, currency, in_stock)`
  from the default module seed. Each row is one scrape observation.
- The four monitored source IDs are `1`, `6`, `9`, and `12`.
- The reporting interval is `2025-01-01 00:00:00` inclusive to
  `2025-01-03 00:00:00` exclusive. Use `captured_at` as stored. An observation
  exactly on the hour belongs to the hour that starts at that timestamp.

## What's required

Return one row per monitored source and hourly bucket, for a total of 192 rows.
Use these columns in this order.

- `source_id` — the monitored source ID.
- `hour_start` — the hour's starting timestamp, including hours without observations.
- `snapshot_count` — the number of observations for that source and hour, including
  both in-stock and out-of-stock observations. Use `0` for an empty hour.
- `in_stock_share` — the number of in-stock observations divided by `snapshot_count`,
  rounded to four decimal places. Return `NULL` for an empty hour and `0` when
  observations exist but all show out-of-stock products.

Row order is arbitrary.

## Completion criteria

Write your query into `src/query.sql`. From the module root, run the validator
against the default seeded database.

```bash
uv run python validate.py 08
```

The validator must print `PASSED`. It compares all 192 rows with the expected
report, including empty hours, hours with only out-of-stock observations, and
hours with a mix of in-stock and out-of-stock observations.

## Estimated evenings

1

## Topics to read up on

- Timestamp series and half-open intervals
- Outer joins and missing observations
- Conditional aggregation and numeric division
