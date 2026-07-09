# Authoring notes: tasks 03, 05, 06, 08 (spoilers)

Off-limits for learners before attempting the corresponding task. Read
`../seed/schema.sql`'s header comments first for the full defect list this
references by letter.

All measurements below taken on the live dev container
(`02-sql-optimization-postgres-1`, Postgres 16, `shared_buffers=1GB`,
`order_items` 13.8M rows / `products` 2.0M / `reviews` 3.0M). Numbers are
machine-local and only meant to justify the calibrated thresholds in each
task's `tests/check.py` — they are not asserted as absolutes anywhere.

## 03-order-detail-join

- Defect: (b). `order_items` has one composite index,
  `idx_order_items_product_order (product_id, order_id)`, and no index
  leading with `order_id`. `q03.sql` filters `WHERE oi.order_id = 4242`.
- Stock symptom (measured): `EXPLAIN ANALYZE` shows `Seq Scan` on
  `order_items` inside a `Nested Loop` under `Gather Merge` — the planner
  cannot use the existing composite index at all for an `order_id`-only
  predicate (leftmost-prefix rule), so it falls back to a parallel seq scan
  of 13.8M rows for a single order. Baseline median (`baseline.py`, 1
  warm-up + 5 runs): **240.5 ms**.
- Intended fix family: add an index on `order_items` whose leading column
  is `order_id` (plain `(order_id)` or composite `(order_id, product_id)`
  both work; the composite avoids a heap fetch for the join key too).
- Verified in a rolled-back `BEGIN`: `CREATE INDEX ... ON order_items
  (order_id, product_id)` (build time ~4.5s at this row count). Resulting
  plan: `Sort` -> `Nested Loop` -> `Index Scan` on the new index +
  `Index Scan` on `products_pkey`. Timed median after fix: **~0.46 ms**
  -> measured speedup **~522x**.
- Threshold set in `check.py`: `MIN_SPEEDUP = 100.0` (roughly 1/5 of
  measured, generous margin for slower dev machines / cold cache).
- Structural checks: forbid `Seq Scan` on `order_items`; require an
  `Index Scan`-family node on `order_items`; then, independently of the
  plan node label, look up the winning index's `indexdef` in `pg_indexes`
  and assert its first column is literally `order_id` (catches a learner
  who reaches an index scan via some unrelated, still-wrong index).

## 05-jsonb-containment

- Defect: (d), the JSONB half. `products.attrs` has no GIN index; `q05.sql`
  filters `attrs @> '{"brand": "Peakline"}' AND price < 150`, then
  `ORDER BY created_at DESC LIMIT 48`.
- Stock symptom (measured): `Seq Scan` on `products` (parallel, 3 workers)
  feeding a `Sort` under `Gather Merge`. Baseline median: **158.0 ms**.
- Intended fix family: `CREATE INDEX ... ON products USING gin (attrs)`
  (default `jsonb_ops`) or `USING gin (attrs jsonb_path_ops)`. Both turn the
  containment filter into a `Bitmap Heap Scan` / `Bitmap Index Scan` pair.
  The `ORDER BY ... LIMIT` still costs a real (if now much smaller) sort
  after the bitmap heap scan — the GIN index does not remove that, only the
  filtering cost. This is the didactic point of hint-3.
- Selectivity measured: `attrs @> '{"brand": "Peakline"}'` matches 34,616
  rows (~1.7% of the table); adding `price < 150` narrows to 32,125.
- Verified in a rolled-back `BEGIN`, two variants:
  - `gin (attrs)` (jsonb_ops): build ~5.1s; timed median after fix (2
    warm-ups, 3 runs) **~50 ms** -> speedup **~3.2x**.
  - `gin (attrs jsonb_path_ops)`: timed median **~37 ms** -> speedup
    **~4.3x**.
  Both plans: `Limit` -> `Sort` -> `Bitmap Heap Scan` -> `Bitmap Index
  Scan`.
- Threshold set in `check.py`: `MIN_SPEEDUP = 2.0`. Note this task does not
  follow the "~1/4 of measured" rule literally — the raw speedup (~3-4x) is
  small enough that a naive 1/4 (~0.8x) would accept a regression, so the
  bar was set below the worse-performing (`jsonb_ops`) variant with margin
  instead. Both real fixes clear the SLA (p95 < 80 ms) comfortably; the
  timing check is a secondary signal to the plan-shape checks here, not the
  primary pass criterion.

## 06-trigram-search

- Defect: (d), the ILIKE half. `products.title` has no trigram index;
  `q06.sql` runs `WHERE title ILIKE '%titanium%' ORDER BY price ASC LIMIT
  50` — a leading-wildcard pattern, so no B-tree (even one built for
  prefix `LIKE`) can help.
- Stock symptom (measured): `Seq Scan` on `products` (parallel) feeding a
  `Sort` under `Gather Merge`. Baseline median: **460.5 ms**.
- Intended fix family: `CREATE EXTENSION pg_trgm;` then
  `CREATE INDEX ... ON products USING gin (title gin_trgm_ops);`. This is
  the one task requiring both an extension and an index — `fix.sql` needs
  two statements.
- Verified in a rolled-back `BEGIN`: extension + index build ~12.7s.
  Resulting plan: `Limit` -> `Sort` -> `Bitmap Heap Scan` -> `Bitmap Index
  Scan` on the new trigram index. Timed median after fix: **~18.5 ms** ->
  measured speedup **~24.9x**.
- Threshold set in `check.py`: `MIN_SPEEDUP = 6.0` (~1/4 of measured,
  per the standard rule).
- `check.py` special-cases the stock failure: if the forbidden `Seq Scan`
  is found *and* `pg_trgm` is absent from `pg_extension`, it prints a
  distinct, didactic reason ("extension missing -- that is part of the
  fix") instead of the generic plan-assertion message.

## 08-index-audit-reviews

- Defect: (e). `reviews` carries five indexes: `reviews_pkey`,
  `idx_reviews_product_id (product_id)`,
  `idx_reviews_product_id_created_at (product_id, created_at)`,
  `idx_reviews_product_id_rating (product_id, rating)`, and
  `idx_reviews_review_text (review_text)`.
  `idx_reviews_product_id` is a strict prefix of both composites (fully
  redundant for any `product_id`-only lookup). `idx_reviews_review_text`
  indexes the entire review body and is not read by anything in the
  invented workload.
- `src/workload.md` (given to the learner) documents three read patterns,
  chosen so that both composites are independently justified and the plain
  `product_id` index and the `review_text` index are not:
  1. "recent reviews for a product" -> needs `(product_id, created_at)`.
  2. "rating summary for a product" (`GROUP BY rating`) -> needs
     `(product_id, rating)` (served as `Index Only Scan`).
  3. "review count for a product" (bare `COUNT(*)`) -> served by either
     composite; used in the checker as a second witness that dropping the
     plain index doesn't regress anything.
  Write rate stated as 50-200 inserts/min steady state (bursting higher),
  no `UPDATE`/`DELETE` — chosen to make the write-amplification argument
  concrete without needing a hard SLA number.
- Verified in a rolled-back `BEGIN`: after `DROP INDEX idx_reviews_product_id;
  DROP INDEX idx_reviews_review_text;`, all three workload queries (tested
  against the product with the *most* reviews, 965,694 rows / ~32% of the
  table -- the least favorable selectivity case) still resolve via
  `Index Scan` / `Index Only Scan`, never `Seq Scan`. Confirms the two
  surviving composites fully cover the documented workload even at worst
  selectivity.
  - Sample single-row `INSERT` timing (rolled back, 20 runs, 2 warm-ups):
    ~0.41 ms median with 3 indexes (pkey + 2 composites) vs. a separate
    500-row batch-insert comparison done earlier in the same investigation:
    ~45.1 ms/500 rows with all 4 non-pkey indexes present vs. ~29.7 ms/500
    rows with only the 2 composites (pkey unavoidable either way) -- roughly
    a **1.5x** reduction in insert-side index-maintenance cost from
    dropping 2 of 4 secondary indexes.
- `check.py` has no timing pass/fail threshold for this task, per spec —
  the batch-insert timing is printed as `info` only. Pass/fail is entirely
  structural: (a) `idx_reviews_product_id` and `idx_reviews_review_text`
  absent from `pg_indexes`, (b) all three workload queries, re-run live,
  avoid `Seq Scan` on `reviews` and hit an index.
- Product used for the checker's workload replay is chosen dynamically at
  check time (`GROUP BY product_id ORDER BY count(*) DESC LIMIT 1`), not
  hardcoded, so it stays valid regardless of exact generated IDs.

## Verification method used for all four

For each task: (1) ran the unmodified `check.py` against the stock DB and
recorded the exact final `NOT PASSED:` line; (2) opened one `psycopg`
connection, `BEGIN`, applied the reference fix DDL directly (never written
into any task's `src/fix.sql`, never committed to the repo), ran
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` through that same connection, fed
the resulting dict to `plan_check.forbid_node` / `require_node` directly,
confirmed all structural assertions pass, timed the query in-transaction to
calibrate the speedup threshold, then `ROLLBACK`; (3) re-queried
`pg_indexes` / `pg_extension` after rollback to confirm the schema is
byte-identical to stock. No `baseline-local.json` was written at the module
root during this work; no throwaway scripts were left in the repository.
