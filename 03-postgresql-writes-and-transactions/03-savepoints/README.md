# 03 — Savepoints

## Backstory

Supplier notes are optional. One duplicate or blank note should leave the rest of the import eligible for commit.

## What's given

The caller opens a transaction and passes note tuples `(source, sku, body)` in input order. The database enforces unique, check, and foreign-key constraints.

## What's required

Implement `import_notes(conn, notes)` in `src/answer.py`. Attempt each insert, recovering inside the caller's transaction after either a unique or check violation. Return the rejected `(source, sku)` keys in input order. Propagate other errors and let the caller commit.

## Completion criteria

PostgreSQL observes all insert attempts. The caller retains its transaction and can commit the valid notes before and after rejected ones. An unknown offer raises a foreign-key violation.

Run from the [module root](../README.md).

```shell
uv run python 03-savepoints/tests/validate.py
```

## Estimated evenings

1

## Topics to read up on

SAVEPOINT, ROLLBACK TO SAVEPOINT, failed transaction state, psycopg nested transaction contexts.
