# 01 — Scoped DML

## Backstory

An operator must correct one imported price without touching nearby versions or another source.

## What's given

The provided schema defines `observations(source, sku, version, cents)`. The validator supplies named parameters and neighboring rows.

## What's required

Complete `src/insert.sql`, `src/update.sql`, and `src/delete.sql`, one statement each. The runner binds `%(source)s`, `%(sku)s`, `%(version)s`, and `%(cents)s`. Use `cents` for insert and update. Use the full observation key to locate the update and delete target. Return `(source, sku, version, cents)` in that order. The target has no current-price reference.

## Completion criteria

The checker compares every changed and returned row, verifies that a negative price is rejected, and checks that deleting a missing row returns zero rows.

Run from the [module root](../README.md).

```shell
uv run python 01-scoped-dml/tests/validate.py
```

## Estimated evenings

1

## Topics to read up on

INSERT, UPDATE, DELETE, RETURNING, composite keys, CHECK constraints.
