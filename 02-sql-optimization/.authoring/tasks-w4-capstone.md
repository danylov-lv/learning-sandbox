# Authoring notes: task 14 (capstone-full-audit) (spoilers)

Off-limits for learners before attempting the corresponding task. Read
`../seed/schema.sql`'s header comments first for the full defect list this
references by letter. This task is a synthesis capstone: eight new
workload queries (`workload/qc01.sql`..`qc08.sql`), each exercising one or
more of the defects from `seed/schema.sql`, with different text than
tasks 01-13's queries.

All measurements below taken on the live dev container
(`02-sql-optimization-postgres-1`, Postgres 16, `shared_buffers=1GB`),
2026-07-08, stock (fully reseeded) database: `orders` 6.0M rows / ~621k-624k
dead tuples, `payments` 5.74M rows / ~481k dead, `inventory_events` 9.0M
rows / ~450k dead, `products` 2.0M, `order_items` 13.8M, `users` 1.0M,
`sellers` 40k, `reviews` 3.0M. Numbers drift slightly run to run (concurrent
authoring/dev activity on the shared server); ratios and speedup factors are
what the checkers gate on, not absolute milliseconds.

Official baselines (via `tools/baseline.py record`, 1 warm-up + 5 runs each,
recorded then removed from the shared `baseline-local.json` per the
verification protocol -- see the closing section):

| id   | median (ms) |
|------|-------------|
| qc01 | 230.1       |
| qc02 | 234.6       |
| qc03 | 241.6       |
| qc04 | 180.1       |
| qc05 | 70.6        |
| qc06 | 356.0       |
| qc07 | 372.7       |
| qc08 | 574.8       |

## qc01 -- order history tab, filtered by status

- Defect (a), same root cause as tasks 01/02/04, different query shape:
  `WHERE user_id = 2 AND status IN ('delivered','shipped') ORDER BY
  created_at DESC LIMIT 50` (task 01/02/04 use `user_id = 42` with no
  status filter or a different projection; this adds an `IN` list).
- Stock plan: `Limit -> Gather Merge -> Sort -> Seq Scan orders` (parallel).
  Baseline median: 230.1 ms.
- Fix family: composite index `orders (user_id, created_at DESC)` --
  identical shape to task 01's reference fix; reused directly in the
  combined-fix verification below.
- Verified (rolled back): fixed plan `Limit -> Index Scan orders
  idx_orders_user_created`, no Seq Scan, no Sort. Fixed median: 0.43-0.50 ms
  across repeated runs -> speedup ~460-530x.
- `check_cp2.py` gate: forbid `Seq Scan` on `orders`; require `Index Scan`
  (family) on `orders`. `MIN_SPEEDUP = 50.0` (~1/9 of measured, matches task
  01's own margin choice since it's the same index).

## qc02 -- order total reconciliation

- Defect (b), same root cause as task 03, different query shape: an
  aggregate join (`SUM(quantity*unit_price)` grouped by order) instead of
  task 03's flat item listing with product titles.
- Stock plan: `Aggregate -> Nested Loop -> Index Scan orders_pkey ->
  Gather -> Seq Scan order_items` (parallel) -- `order_items` has no index
  leading with `order_id`. Baseline median: 234.6 ms.
- Fix family: index on `order_items` leading with `order_id` (used
  `(order_id, product_id)`, same shape as task 03's reference fix).
- Verified (rolled back): fixed plan `Aggregate -> Nested Loop -> Index Scan
  orders_pkey -> Index Scan order_items idx_order_items_order_product`.
  Fixed median: 0.39-0.48 ms -> speedup ~490-600x.
- `check_cp2.py` gate: forbid `Seq Scan` on `order_items`; require
  `Index Scan` (family) on `order_items`. `MIN_SPEEDUP = 100.0` (~1/5 of
  measured, matches task 03's margin choice for the same index shape).

## qc03 -- inventory corrections audit

- Defect (c), the recent-window half, exercised differently than tasks
  09/10: `WHERE event_type = 'correction' AND occurred_at >= now() -
  interval '30 days' GROUP BY product_id ORDER BY correction_count DESC
  LIMIT 50` -- an aggregate over a *combination* of an unindexed
  (`event_type`) and an indexed (`occurred_at`) predicate, not task 09's
  deep-pagination shape or task 10's plain recency filter.
- Stock plan: `Limit -> Sort -> Aggregate -> Index Scan
  idx_inventory_events_occurred_at` (est 1006 rows, act 103,232 -- also
  carries a ~100x row-estimate error, not gated on here but visible in the
  plan). Baseline median: 241.6 ms.
- **Two accepted fix families, deliberately, per spec:**
  - *Index fix*: `CREATE INDEX ... ON inventory_events (event_type,
    occurred_at) INCLUDE (product_id, qty_delta)`, with the old
    single-column `occurred_at` index dropped (the planner otherwise keeps
    preferring the old index even with the new one present -- confirmed:
    with both indexes coexisting, the plan is unchanged; only after
    dropping `idx_inventory_events_occurred_at` does the new composite get
    chosen). Verified (rolled back): plan becomes `Limit -> Sort ->
    Aggregate -> Sort -> Index Only Scan idx_ie_type_occurred`. Fixed
    median: 46.4-58.3 ms across variants -> speedup ~4.1-5.2x. `Heap
    Fetches` on the Index Only Scan node equals rows read (no vacuum has
    run -- same pathology as tasks 04/11; not gated on here).
  - *Partitioning fix*: full copy-and-swap migration, same recipe as task
    10 (22 monthly partitions Jan 2025 - Oct 2026, `INSERT ... SELECT`,
    rename-swap, indexes on `occurred_at` and `product_id` recreated on the
    parent). Build time ~7-8s insert + ~2-3s indexes, well under a minute.
    Verified (rolled back): plan becomes `Append` over 5 partition children
    (2 with real matching rows -- the current and previous month -- plus 3
    future empty ones, because the query's lower-bound-only predicate with
    no upper bound statically matches every partition whose range extends
    past the cutoff, identical finding to task 10's authoring notes).
    Fixed median: ~90-99 ms (one clean run) -> speedup ~2.4-2.7x -- real,
    but modest, same reason task 10 documented (the table already had a
    usable index on the filtered column; partitioning mainly shrinks how
    much of it gets walked, not whether an index gets used at all).
- **`check_cp2.py` gate, accepting either family**: an `Index Only Scan` on
  `inventory_events` (index-fix signature, absent from every stock/
  partition-only plan observed) OR `inventory_events` being a partitioned
  table (`pg_partitioned_table`) with the executed plan touching at most 8
  partitions (generous margin above the 5 observed, to tolerate a learner
  building extra future headroom). No hard `MIN_SPEEDUP` -- the two
  accepted fixes differ by roughly 2x in real speedup (5x vs. 2.5x), so
  per the module's established pattern (see task 10's notes) timing is
  reported as `info` only; the structural either/or gate is primary.
- **Important interaction found while calibrating the combined-fix
  transaction**: building the composite index *and* leaving the old
  single-column index in place does **not** change the plan -- Postgres
  keeps using the old index regardless. The reference fix's index-family
  branch requires actually dropping `idx_inventory_events_occurred_at`, not
  merely adding the new index alongside it. Documented here because a
  learner who "adds an index but doesn't touch the old one" will see no
  improvement and might reasonably conclude the index approach doesn't
  work for this query -- it does, but only once the old index stops
  shadowing it.

## qc04 -- brand + color facet search

- Defect (d), the JSONB half, exercised with a two-key containment filter
  (`attrs @> '{"brand": "Nexara", "color": "green"}'`) instead of task 05's
  single-key filter combined with a price range.
- Stock plan: `Limit -> Gather Merge -> Sort -> Seq Scan products`
  (parallel). Baseline median: 180.1 ms.
- Fix family: `CREATE INDEX ... ON products USING gin (attrs)` (default
  `jsonb_ops`), same as task 05.
- Verified (rolled back): fixed plan `Limit -> Gather Merge -> Sort ->
  Bitmap Heap Scan products -> Bitmap Index Scan idx_products_attrs_gin`.
  Fixed median: 59.2-66.4 ms -> speedup ~2.7-3.0x.
- **Bug found while calibrating this gate, same one task 02's author
  documented**: `Bitmap Index Scan` nodes never carry their own `Relation
  Name`/`Alias`, and `Bitmap Heap Scan` (which does carry it) is not in
  `plan_check.py`'s `"Index Scan"` family set, so `require_node(plan,
  "Index Scan", table="products")` cannot match either node in this fixed
  plan. Fixed the same way task 02's checker did: drop the `table=`
  qualifier on this one `require_node` call (safe -- single-table query,
  `forbid_node` above is still scoped).
- `check_cp2.py` gate: forbid `Seq Scan` on `products`; require `Index
  Scan` (unscoped). `MIN_SPEEDUP = 1.5` -- per task 05's precedent, the raw
  speedup here (~2.7-3.0x) is modest enough that the standard "~1/4 of
  measured" rule would set too generous a floor relative to how noisy a
  ~60ms measurement can be; the bar sits below the weaker observed variant
  with margin instead.

## qc05 -- stuck-in-processing count

- Defect (g), same root cause as task 07, deliberately different query
  shape: a single-table aggregate (`count(*)`, `avg(total_amount)`) with no
  join, instead of task 07's `orders JOIN users` ops-queue shape -- this
  isolates the stats-misestimate finding from any join-cardinality
  interaction.
- Stock plan: `Aggregate -> Bitmap Heap Scan orders -> Bitmap Index Scan
  idx_orders_status` (est 12, act 7793 at the heap-scan node -> ~649x row-
  estimate error). Baseline median: 70.6 ms.
- Fix family: `ANALYZE orders` (statistics target left at its stock value
  of 10 -- per task 07's own finding, `orders.status` only has 7 distinct
  values, so target 10 already captures all of them once the sample is
  current; staleness, not target size, is the actual defect).
- Verified (rolled back): `ANALYZE orders` alone (no other index) leaves
  the same `Bitmap Heap Scan` shape but with the estimate corrected to
  ~2.2-2.9x error (est 3451-3679 vs. act 7791-7793) and essentially
  unchanged timing (~70-75 ms) -- the estimate fix alone doesn't move the
  needle on raw speed here, since the query still has to touch the same
  matching rows either way. **When the combined fix's `orders(created_at)`
  index (built for qc06/07/08) is also present**, the planner additionally
  chooses a `BitmapAnd` combining `idx_orders_status` and the new
  `idx_orders_created_at`, and *that* does meaningfully cut timing (~20-24
  ms, a genuine ~3x win) -- a nice opportunistic side effect of a fix built
  for other queries, but not something qc05's own fix guarantees on its
  own. `check_cp2.py` therefore has no `MIN_SPEEDUP` gate for qc05 (same
  design choice as task 07): the structural row-estimate-error gate is the
  only pass/fail signal; timing is reported as `info`.
- **Bug found while calibrating this gate**: `tools/plan_check.py`'s
  `rows_estimate_error()` walks every node including `BitmapAnd`, which
  reports `Actual Rows = 0` unconditionally (it produces a bitmap, not
  tuples) -- once the combined-fix transaction's second index makes a
  `BitmapAnd` appear, this manufactures a spurious ~3400x "worst error" at
  the `BitmapAnd` node itself, even though the real child nodes underneath
  it show a genuine, much smaller ~2-3x error. Since `tools/plan_check.py`
  is shared infrastructure outside this task's directory, `check_cp2.py`
  and `check_cp3.py` each define their own local estimate-error walker that
  skips `BitmapAnd`/`BitmapOr` nodes rather than importing
  `rows_estimate_error` directly, with the discrepancy documented inline.
- `check_cp2.py` / `check_cp3.py` gate: worst estimate error (BitmapAnd-
  aware) <= 50.0x. Stock: 649.2x (fails by >10x). Fixed (ANALYZE only):
  2.9-3.2x across every variant tested, including inside the full combined-
  fix transaction (3.08x) and a solo in-txn ANALYZE re-check (3.16x).

## qc06 -- refund reconciliation

- **New ground**: a payments-side query, joining `orders` to `payments`
  filtered by payment status and an order-date window --
  `WHERE p.status = 'refunded' AND o.created_at >= now() - interval '7
  days'`. `payments` has indexes on `order_id` and `external_ref` only
  (defect (i)'s column) -- nothing on `status` or `created_at`, and nothing
  on `orders.created_at` alone (only `idx_orders_status`, per defect (a)/
  (g)'s territory).
- Considered and rejected during design: the same query with `p.status =
  'captured'` (the dominant payments status, ~86% of the table) instead of
  `'refunded'` (~5.4%). With `'captured'`, the post-fix plan is highly
  sensitive to whether `ANALYZE` has run: pre-ANALYZE it's a cheap `Nested
  Loop` (~107 ms), post-ANALYZE the planner switches to `Hash Join` + `Seq
  Scan payments` (~212-304 ms) because `'captured'` is too unselective for
  any index to help the payments side regardless of join strategy, and the
  cost model judges the seq-scan-based plan cheaper. This made the query's
  *outcome* (not just its plan shape) depend on operation order in a way
  that felt like an unfair moving target for a capstone gate, so the
  workload query uses `'refunded'` instead -- selective enough (~5.4% of
  payments) that an index-driven access path is unambiguously the right
  answer, even though the ANALYZE-order sensitivity on the *orders* side
  (see below) still shows up in the timing.
- Stock plan: `Aggregate -> Gather -> Aggregate -> Nested Loop -> Seq Scan
  orders -> Index Scan payments idx_payments_order_id` (parallel) -- the
  Seq Scan on `orders` for the date-only filter is the dominant cost, since
  `orders` has no index usable for a bare `created_at` range. Baseline
  median: 356.0 ms.
- Fix family: `CREATE INDEX ... ON orders (created_at)`.
- **Verified (rolled back), two variants, depending on whether `ANALYZE
  orders` has also run** (both legitimate, both observed with only this one
  index present):
  - Without a fresh `ANALYZE` (stale `orders.status`/`created_at`
    cross-correlation stats): plan becomes `Aggregate -> Nested Loop ->
    Index Scan orders idx_orders_created_at -> Index Scan payments
    idx_payments_order_id`. Fixed median: 100.6-102.1 ms -> speedup
    ~3.5-3.6x.
  - With `ANALYZE orders` also run (as qc05's fix requires, and as any
    reasonable learner doing the whole audit would do): plan becomes
    `Aggregate -> Gather -> Aggregate -> Hash Join -> Seq Scan payments ->
    Hash -> Index Scan orders idx_orders_created_at`. Fixed median:
    204.1-220.7 ms -> speedup ~1.6-1.8x -- real, but noticeably smaller,
    because the planner's now-accurate row estimate for the date filter
    (tens of thousands of matching orders) makes a single `Seq Scan` over
    `payments` look cheaper than repeated index probes, even though the
    nested-loop variant is empirically faster in this specific case. This
    is a genuine planner-cost-model quirk, not a bug in the fix.
  - Confirmed identically inside the full combined-fix transaction (all
    six reference indexes + `ANALYZE orders` together): qc06 lands in the
    `Hash Join`/`Seq Scan payments` shape, median 211-217 ms across
    repeated combined-transaction runs -> speedup ~1.6-1.7x against the
    356.0 ms baseline.
- **`check_cp2.py` gate, designed around this interaction**: forbid `Seq
  Scan` on `orders`; require `Index Scan` (family) on `orders`.
  Deliberately does **not** forbid `Seq Scan` on `payments` -- both
  verified plan variants keep `orders` off a Seq Scan, but only one of them
  also avoids scanning `payments`, and both are legitimate outcomes of the
  same correct fix. `MIN_SPEEDUP = 1.3` -- set below the weaker
  (post-ANALYZE) measured variant (~1.6-1.8x) with margin, same "modest
  speedup, structural gate carries more weight" pattern as qc04/task05,
  documented here because the reason is specific to this query (an
  ANALYZE-order interaction) rather than an inherently small fix.

## qc07 -- regional recent-orders feed

- **New ground**: `orders JOIN users ON u.id = o.user_id` (defect (h)'s
  `int4`-vs-`int8` join), filtered by `u.country = 'DE'` and a 7-day
  `o.created_at` window, instead of task 07's `status`-filtered ops-queue
  join. Chosen specifically to check whether the type mismatch blocks
  index-based join execution in PG16, per the task brief.
- **Finding on defect (h)**: it does not block index usage. In every plan
  observed (stock and fixed), the inner side of the join
  (`Index Scan users_pkey` or `Memoize` wrapping it) uses the primary key
  index normally despite the `bigint`/`integer` type difference -- Postgres
  implicitly promotes `int4` to `int8` for the comparison and can still use
  a btree index scan on the `int4` side. The query is slow on stock for an
  entirely different, unrelated reason (see below); defect (h) is
  report-only material here, exactly as the task spec anticipated. `REPORT.md`
  section 7 is where this belongs, not the workload's fix criteria.
- Stock plan: `Limit -> Nested Loop -> Seq Scan orders -> Memoize -> Index
  Scan users users_pkey` (parallel) -- the real cost driver is the `Seq
  Scan` on `orders` for the bare `created_at` range filter (same missing-
  index gap as qc06). Baseline median: 372.7 ms.
- Fix family: the same `orders (created_at)` index as qc06 -- this query
  needed no separate fix, a nice "one fix, two queries" finding for the
  report's fix-plan prioritization.
- Verified (rolled back): fixed plan `Limit -> Nested Loop -> Index Scan
  orders idx_orders_created_at -> Memoize -> Index Scan users users_pkey`.
  Stable across both ANALYZE states tested (unlike qc06 -- this shape
  never flips to a Hash Join/Seq Scan variant in any variant tried,
  including inside the full combined-fix transaction). Fixed median:
  0.91-1.29 ms across repeated runs -> speedup ~290-410x.
- `check_cp2.py` gate: forbid `Seq Scan` on `orders`; require `Index Scan`
  (family) on `orders`. `MIN_SPEEDUP = 30.0` -- generous margin (~1/10-1/13
  of measured) since sub-millisecond timings carry more relative noise than
  the module's usual comparisons.

## qc08 -- seller revenue leaderboard (last 6 hours)

- **New ground**, combining defects (a) and (b) in one query on purpose:
  `sellers JOIN products JOIN order_items JOIN orders`, filtered only by
  `o.created_at >= now() - interval '6 hours'`, grouped by seller. A
  4-table join exercising both the missing `orders(created_at)`-style gap
  and `order_items`'s wrong-leading-column index at once -- a "why is this
  report so slow" showcase deliberately built to have more than one root
  cause.
- **Window tuning, important finding**: at wider windows (2 days, 30 days),
  even with both reference indexes in place, the planner chooses `Hash
  Join` + unconditional `Seq Scan order_items` (13.8M rows) regardless of
  how selective the `orders` side is, because the join's estimated result
  size (tens/hundreds of thousands of rows) makes a full scan + hash join
  genuinely cheaper than looping an index probe that many times -- a
  defensible planner decision, not a bug, but it meant a 2-day-window
  version of this query only sped up ~2.2x post-fix (1816 ms -> ~840 ms)
  and a 30-day version showed almost no headline win. Narrowed the window
  to 6 hours specifically so the *number of matching orders* stays small
  enough (~530-540 orders observed) that a `Nested Loop`-based plan
  remains the cost-model's pick regardless of whether `ANALYZE orders` has
  also run -- confirmed stable in both states, unlike qc06.
- Stock plan (6-hour window): `Limit -> Sort -> Aggregate -> Gather Merge
  -> Aggregate -> Sort -> Nested Loop -> Nested Loop -> Hash Join -> Seq
  Scan order_items -> Hash -> Seq Scan orders ... -> Index Scan products
  products_pkey ... -> Index Scan sellers sellers_pkey` (parallel).
  Baseline median: 574.8 ms.
- Fix family: `orders (created_at)` (same index as qc06/07) +
  `order_items (order_id, product_id)` (same index as qc02) -- again, no
  new DDL beyond what other queries in this workload already need.
- Verified (rolled back): fixed plan collapses to a `Nested Loop` chain --
  `orders idx_orders_created_at -> order_items
  idx_order_items_order_product -> products products_pkey -> sellers
  sellers_pkey` -- no `Seq Scan` anywhere, no `Hash Join`. Stable across
  both ANALYZE states and inside the full combined-fix transaction. Fixed
  median: 3.8-4.8 ms across every variant tested -> speedup ~120-151x.
- `check_cp2.py` gate: forbid `Seq Scan` on both `order_items` and
  `orders`; require `Index Scan` (family) on `order_items`.
  `MIN_SPEEDUP = 20.0` (generous margin against a >100x measured speedup,
  same reasoning as qc07 -- small absolute timings, more relative noise).

## Combined-fix verification (all six reference indexes + ANALYZE together)

Applied in one rolled-back transaction, matching every query's individually
verified fix:

```
CREATE INDEX idx_orders_user_created ON orders (user_id, created_at DESC);
CREATE INDEX idx_order_items_order_product ON order_items (order_id, product_id);
CREATE INDEX idx_products_attrs_gin ON products USING gin (attrs);
CREATE INDEX idx_orders_created_at ON orders (created_at);
CREATE INDEX idx_ie_type_occurred ON inventory_events (event_type, occurred_at) INCLUDE (product_id, qty_delta);
DROP INDEX idx_inventory_events_occurred_at;
ANALYZE orders;
```

Build time for all five new indexes + the drop: ~19.4-19.7s (dominated by
the GIN index on `products.attrs`, ~5s, and the composite index on
`inventory_events`, several seconds at 9M rows). All eight `check_cp2.py`
structural gates passed against this combined state (verified by importing
`check_cp2`'s gate functions directly and running them against `EXPLAIN`
output taken through the same open transaction -- `plan_check.get_plan()`
opens its own connection and cannot see uncommitted DDL, so it could not be
used as a black box here; same workaround task 10's author used for their
migration verification). All eight timing comparisons against the
recorded stock baselines cleared their `MIN_SPEEDUP` threshold (see the
per-query numbers above -- the tightest margin was qc06 at ~1.6x against a
1.3x floor). The qc03 partitioning fix family was verified separately (its
own rolled-back transaction, since it structurally conflicts with the
index-fix family -- you can't have both a covering composite index on an
unpartitioned table and a partitioned table with the composite index's
table renamed away in the same test) and passed the accept-either gate via
the partition-count branch (5 partitions touched, within the margin of 8).

After rollback, re-queried `pg_indexes`, `pg_class.reloptions`,
`pg_attribute.attstattarget`, `pg_stats.most_common_freqs`, and
`pg_class.relkind`/row counts for every touched table: all byte-identical
to the pre-verification stock state (index lists match exactly what
`seed/schema.sql` creates; `orders.status` statistics target still 10;
`pg_stats.most_common_freqs` for `orders.status` back to its stock values
`[0.7782, 0.0824, 0.0520, 0.0379, 0.0206, 0.0197, 0.0093]`, confirming
`ANALYZE` truly rolls back its `pg_statistic` effects, not just its visible
side effects -- checked explicitly before relying on in-transaction
`ANALYZE` anywhere in this task's checkers/verification; `inventory_events`
is an ordinary heap (`relkind = 'r'`), not partitioned, with its original
three indexes; row counts unchanged: `orders` 6,000,000, `inventory_events`
9,000,000).

## CP3 hygiene gates

- **Vacuum hygiene** (`orders`/`payments`/`inventory_events`): identical
  catalog gates to `11-vacuum-debt/tests/check.py` (`autovacuum_enabled=off`
  absent from reloptions, `last_vacuum`/`last_autovacuum` not both NULL,
  dead-tuple ratio < 0.02). Not re-verified end-to-end here since `VACUUM`
  cannot run inside a transaction and cannot be rolled back -- the pass
  path was already scratch-verified end-to-end by task 11's author (see
  `.authoring/tasks-w3c.md`, "Scratch-DB verification protocol") against a
  disposable database on the same server, and that verification is
  inherited rather than repeated. The fail path (stock DB, no scratch
  needed) was re-confirmed live for this task: all nine structural checks
  (three tables x three sub-gates) fail exactly as expected.
- **Redundant-index gate** (`reviews`): identical to
  `08-index-audit-reviews/tests/check.py` (`idx_reviews_product_id` and
  `idx_reviews_review_text` must be absent). Verified in a rolled-back
  transaction: dropping both, the gate function reports `PASS` with no
  failures. Fail path confirmed live against stock (both indexes present).
- **Statistics freshness** (`orders.status`): a probe query shaped like
  qc05 (`count(*) FROM orders WHERE status = 'processing' AND created_at
  >= now() - interval '14 days'`), gated on the same BitmapAnd-aware worst
  row-estimate error as `check_cp2.py`'s qc05 gate, bound 50.0x. Verified
  in a rolled-back transaction with an in-txn `ANALYZE orders` (confirmed
  separately, see above, that this rolls back `pg_statistic` exactly):
  worst error 3.16x, comfortably under the bound. Fail path confirmed live
  against stock: 649.2x.
- **REPORT.md sections 5-8**: parsed the same way as CP1's sections 1-4 --
  heading presence by number, section 5's table checked for a non-empty
  last cell per `qcNN` row. Verified with a temporary `REPORT.md` (copied
  from `REPORT_TEMPLATE.md`, every table cell filled with a placeholder
  value, never committed) that the parser accepts a complete report and
  rejects an incomplete one; the temporary file was deleted immediately
  after.

## CP1 gates

- Verified fail path against stock, no baseline recorded and no
  `REPORT.md`:
  ```
  NOT PASSED: baseline-local.json missing entries for: qc01, qc02, qc03, qc04, qc05, qc06, qc07, qc08 -- run tools/baseline.py record for every workload/qcNN.sql first; REPORT.md not found next to README.md -- copy REPORT_TEMPLATE.md to REPORT.md and fill it in
  ```
- Verified the intermediate state (baselines recorded, `REPORT.md` present
  but only sections 1-2 filled, section 2's table missing several `qcNN`
  rows and one row with an empty root-cause cell): correctly reports the
  missing sections (3, 4) and the missing/empty rows by id, including
  catching a row where every *other* cell was filled but the root-cause
  cell specifically was blank (an early version of the checker's row-
  completeness regex only checked "all cells empty," which missed this
  case -- fixed to check specifically the last cell). Temporary file
  deleted immediately after both intermediate-state tests.

## Exact stock `NOT PASSED` lines (all three checkers, same run)

```
CP1: NOT PASSED: baseline-local.json missing entries for: qc01, qc02, qc03, qc04, qc05, qc06, qc07, qc08 -- run tools/baseline.py record for every workload/qcNN.sql first; REPORT.md not found next to README.md -- copy REPORT_TEMPLATE.md to REPORT.md and fill it in
```
```
CP2: NOT PASSED: qc01: forbidden node present: Seq Scan on table 'orders' (found 1x on: orders); qc02: forbidden node present: Seq Scan on table 'order_items' (found 1x on: order_items); qc03: no Index Only Scan on inventory_events, and inventory_events is not a partitioned table -- neither accepted fix family is present; qc04: forbidden node present: Seq Scan on table 'products' (found 1x on: products); qc05: worst row-estimate error 649.2x > 50.0x (Bitmap Heap Scan on orders) -- pg_stats on orders.status still looks stale; qc06: forbidden node present: Seq Scan on table 'orders' (found 1x on: orders); qc07: forbidden node present: Seq Scan on table 'orders' (found 1x on: orders); qc08: forbidden node present: Seq Scan on table 'order_items' (found 1x on: order_items)
```
```
CP3: NOT PASSED: orders: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); orders: never vacuumed (last_vacuum and last_autovacuum both NULL); orders: dead-tuple ratio 0.1035 >= 0.02; payments: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); payments: never vacuumed (last_vacuum and last_autovacuum both NULL); payments: dead-tuple ratio 0.0838 >= 0.02; inventory_events: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); inventory_events: never vacuumed (last_vacuum and last_autovacuum both NULL); inventory_events: dead-tuple ratio 0.0500 >= 0.02; reviews: redundant index(es) still present: idx_reviews_product_id, idx_reviews_review_text; orders.status stats-freshness probe worst estimate error 649.2x > 50.0x (Bitmap Heap Scan on orders) -- pg_stats still looks stale; REPORT.md not found next to README.md
```

## Verification method used for this task

For each of the eight workload queries: (1) measured the stock median via
`tools/baseline.py record` (1 warm-up + 5 runs); (2) opened one `psycopg`
connection, `BEGIN`, applied the reference fix DDL/`ANALYZE` directly
(never written into any shipped file, never committed), ran `EXPLAIN
(ANALYZE, BUFFERS, FORMAT JSON)` through that same connection, fed the
result to the exact gate functions defined in `tests/check_cp2.py` (or
`tests/check_cp3.py` for the stats-freshness and redundant-index gates),
confirmed every structural assertion passes, timed the query
in-transaction to calibrate `MIN_SPEEDUP`, then `ROLLBACK`. All eight
queries' index-family fixes (plus `ANALYZE orders`) were then applied
together in one combined rolled-back transaction (see above) to confirm no
conflicts or shadowing between them; the qc03 partitioning alternative was
verified in a separate rolled-back transaction since it's structurally
incompatible with the index-family fix for the same table. All three
checkers (`check_cp1.py`, `check_cp2.py`, `check_cp3.py`) were run against
the live, unmodified stock database and produced the three distinct
`NOT PASSED` lines recorded above; `check_cp1.py` was additionally run
against an intermediate state (baselines recorded, a partially-filled
temporary `REPORT.md`) to confirm its section/row-level gates work, and
`check_cp3.py`'s report-section gate was checked the same way against a
fully-filled temporary `REPORT.md` copied from `REPORT_TEMPLATE.md` --
every temporary `REPORT.md` was deleted immediately after use and never
left in the repository.

Official baselines were recorded into the shared module-root
`baseline-local.json` for this verification (needed for `check_cp2.py`'s
timing gates to have something to compare against), then the file was
restored to its pre-existing pre-task-14 contents (the `deep_page*`,
`given_query_09`, and `recent_window_stock` entries left behind by earlier
authoring sessions on tasks 09/10) by restoring from a backup copy taken
before this task's baselines were written -- `baseline-local.json` at the
module root carries **no** `qc01`-`qc08` entries after this task's authoring
work, so a learner starting `14-capstone-full-audit` from a freshly reset
database also starts CP1 from zero, as intended.

After all verification: re-confirmed schema/stats byte-identical to stock
(index lists, reloptions, `attstattarget`, `pg_stats.most_common_freqs` for
`orders.status`, row counts, `inventory_events.relkind`) via direct query
against the live `sandbox` database. No `VACUUM`, `VACUUM FULL`, or
committed `ANALYZE`/DDL was ever issued against `sandbox` during this work.
No throwaway scripts were left in the repository; all scratch scripts used
for calibration and the two full-migration-recipe rehearsals (index-fix and
partition-fix variants for qc03) lived under the session scratch directory,
outside the repo, and were not copied in.
