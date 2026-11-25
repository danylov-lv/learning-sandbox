# 05 — COPY and staging

## Backstory

A supplier switches to CSV exports. Load them in bulk and handle repeats within the same file.

## What's given

The header is `source,sku,version,cents`. Offers exist, and duplicate keys agree on cents. The caller opens the transaction. `harness.db.create_staging_table(conn)` creates a typed temporary `price_stage` table.

## What's required

Implement `load_csv(conn, path)` in `src/answer.py`. Use the staging helper, stream the CSV through `COPY ... FROM STDIN`, and merge staged rows into both target tables with set-based statements. Keep the rules from task 04. A malformed integer must propagate as a PostgreSQL error.

## Completion criteria

The checker observes COPY into `price_stage` and validates deduplication, latest prices, replay, and rollback of malformed input.

Run from the [module root](../README.md).

```shell
uv run python 05-copy-staging/tests/validate.py
```

## Estimated evenings

1

## Topics to read up on

COPY FROM STDIN, psycopg copy streaming, temporary tables, INSERT SELECT, per-key deduplication.
