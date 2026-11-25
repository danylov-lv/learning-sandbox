# 02 — Atomic price write

## Backstory

A worker can fail between recording an observation and updating the current price. Readers need to see both writes together.

## What's given

An idle autocommit-enabled connection, one event for an offer with no prices, and a callback. A separate connection observes committed state.

## What's required

Implement `record(conn, event, before_current)` in `src/answer.py`. Start a transaction, insert the history row, call `before_current()`, then insert the current-price row. Propagate callback errors and leave the connection idle.

## Completion criteria

The writer sees the history row during the callback. The reader sees neither row until commit and sees both after success. A callback failure leaves both tables empty.

Run from the [module root](../README.md).

```shell
uv run python 02-atomic-price-write/tests/validate.py
```

## Estimated evenings

1

## Topics to read up on

autocommit, BEGIN, COMMIT, ROLLBACK, psycopg transaction contexts.
