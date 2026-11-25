# 06 — Isolation and snapshots

## Backstory

A stock report reads the same product several times while another session updates it.

## What's given

The reader starts idle with autocommit enabled. The harness starts a writer update after the reader's first read and commits it after the second.

## What's required

Implement `read_snapshots(reader, isolation, sku, after_read)` in `src/answer.py`. Read the quantity three times in one transaction with the requested isolation. Call `after_read(1)`, `after_read(2)`, and `after_read(3)` immediately after each read. Return the three quantities in a tuple and finish the transaction.

## Completion criteria

The validator measures the reader's isolation level and checks all three observations under both levels.

Run from the [module root](../README.md).

```shell
uv run python 06-isolation-snapshots/tests/validate.py
```

## Estimated evenings

1

## Topics to read up on

MVCC snapshots, READ COMMITTED, REPEATABLE READ, setting the transaction isolation level.
