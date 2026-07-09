# 05 — JSONB Containment

## Backstory

Marketing bought a traffic campaign that lands users straight on brand
storefront pages — "Shop all Peakline," that kind of thing. The growth team
is not happy: bounce rate on those pages has doubled since launch. You trace
it to `queries/q05.sql`, the query that renders the storefront grid. It
filters `products.attrs`, a JSONB column, for a brand match, plus a price
cap, sorted by recency. Every field it touches is unindexed for this access
pattern — `attrs` has no index of any kind, and the sort still has to happen
after the filter.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB).
- `queries/q05.sql` — the canonical, screaming query. **Do not modify this
  file.**
- `tools/plan_check.py`, `tools/baseline.py`.
- The live Postgres instance (see module root `docker-compose.yml`);
  `products` has 2.0M rows.
- `src/fix.sql` — empty stub. You write your fix here.

## What's required

1. Record the baseline once:

   ```
   uv run python tools/baseline.py record queries/q05.sql
   ```

2. Diagnose why `attrs @> '{"brand": "Peakline"}'` cannot use any existing
   index, and what kind of index a JSONB containment operator like `@>`
   actually needs.
3. Write the DDL into `05-jsonb-containment/src/fix.sql` and apply it
   against the live database yourself.
4. Only `order_items`, `products`, `reviews` (and read-only FK joins) may be
   touched. Leave `orders`, `users`, `payments`, `inventory_events`,
   `sellers`, `categories` untouched.

Note: `q05.sql` also sorts by `created_at DESC` after filtering. Think
about whether the index you add removes all the cost, or just the filtering
part of it — and whether that's good enough to hit the SLA.

## Completion criteria

Run, from the module root:

```
uv run python 05-jsonb-containment/tests/check.py
```

The checker verifies:

1. No `Seq Scan` on `products` in the `q05.sql` plan.
2. A `Bitmap Index Scan` is present (i.e. the containment filter is served
   by an index, not a full-table scan followed by a JSONB comparison per
   row).
3. The query runs meaningfully faster than your recorded baseline.

## Estimated evenings

1

## Topics to read up on

- JSONB storage and the `@>` containment operator
- GIN indexes: what they index and how bitmap scans use them
- `jsonb_ops` vs. `jsonb_path_ops` GIN operator classes — what each supports
  and what each costs
- Bitmap Heap Scan vs. Bitmap Index Scan, and why a `LIMIT` with `ORDER BY`
  doesn't always get free ordering from an index
