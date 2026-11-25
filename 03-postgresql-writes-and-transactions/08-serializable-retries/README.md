# 08 — Serializable retries

## Backstory

Two scrapers reserve monitoring slots on separate rows. The sum of units must stay within one shared limit.

## What's given

The harness supplies an idle connection, worker key, units, limit, isolation name, and positive attempt budget. It synchronizes the first reads across workers.

## What's required

Implement `reserve(conn, worker, units, limit, isolation, max_attempts, after_read)` in `src/answer.py`. For each attempt, open a transaction at the requested isolation, read the total, and call `after_read(attempt_number, total)` with a one-based attempt number. Return `False` if the request would exceed the limit. Otherwise increment the existing worker row and return `True` after commit. Retry only `40001`, including commit-time failures. Propagate the last failure when attempts run out.

## Completion criteria

The validator reproduces write skew, verifies a real `40001` with a one-attempt budget, observes a fresh read on retry, and rejects retries of unrelated constraint errors.

Run from the [module root](../README.md).

```shell
uv run python 08-serializable-retries/tests/validate.py
```

## Estimated evenings

1–2

## Topics to read up on

write skew, SERIALIZABLE, SQLSTATE 40001, whole-transaction retries.
