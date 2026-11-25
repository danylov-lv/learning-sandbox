# 07 — Row locks and deadlocks

## Backstory

Two stock workers update the same products in opposite orders. Each can hold a lock the other needs.

## What's given

The harness supplies an idle connection per worker, two distinct keys, a delta, an ordering flag, and a callback. It controls the interleaving.

## What's required

Implement `adjust_stock(conn, skus, delta, ordered, after_first)` in `src/answer.py`. In one transaction, explicitly lock both rows before applying the delta to each. With `ordered=False`, follow the supplied order. With `ordered=True`, take locks by ascending SKU. Call `after_first(sku)` immediately after acquiring the first lock. Propagate a deadlock error.

## Completion criteria

The reversed order produces one real deadlock. The ordered run shows a lock wait and commits both adjustments once.

Run from the [module root](../README.md).

```shell
uv run python 07-row-locks-and-deadlocks/tests/validate.py
```

## Estimated evenings

1–2

## Topics to read up on

SELECT FOR UPDATE, row locks, deadlock cycles, SQLSTATE 40P01, pg_blocking_pids.
