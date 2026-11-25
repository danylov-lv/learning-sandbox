# 04 — Idempotent upsert

## Backstory

A scraper retries deliveries and can report an older observation after a newer price is already visible.

## What's given

Each `Event` contains `(source, sku, version, cents)`. A higher version is newer for the same offer. Duplicate observation keys always carry the same cents value. The caller opens the transaction.

## What's required

Implement `apply_events(conn, events)` in `src/answer.py`. Use `INSERT ... ON CONFLICT` for both tables. Store one history row per observation key and the highest known version per offer in current prices. Handle repeats within and across calls.

## Completion criteria

Expect correct history and current prices after late, duplicate, and unrelated observations. A reader sees changes only after commit. The validator inspects live upsert statements.

Run from the [module root](../README.md).

```shell
uv run python 04-idempotent-upsert/tests/validate.py
```

## Estimated evenings

1

## Topics to read up on

INSERT ON CONFLICT, conflict targets, excluded rows, conditional UPDATE.
