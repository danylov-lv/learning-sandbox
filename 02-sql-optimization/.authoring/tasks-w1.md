# Authoring notes: tasks 01, 02, 04, 07 (spoilers)

Off-limits for learners before attempting the corresponding task. Read
`../seed/schema.sql`'s header comments first for the full defect list this
references by letter.

All measurements below taken on the live dev container
(`02-sql-optimization-postgres-1`, Postgres 16, `shared_buffers=1GB`,
`orders` 6.0M rows / 621k dead tuples / `users` 1.0M rows). Numbers are
machine-local and only meant to justify the calibrated thresholds in each
task's `tests/check.py` — they are not asserted as absolutes anywhere.

## 01-read-the-plan

- Defect: (a). `orders` has one index, `idx_orders_status (status)`, and no
  index on `(user_id, created_at)`. `queries/q01.sql` filters
  `WHERE user_id = 42 ORDER BY created_at DESC LIMIT 20`.
- Stock symptom (measured): `EXPLAIN ANALYZE` shows `Limit` -> `Sort` ->
  `Seq Scan` on `orders` (parallel, `Gather Merge` above the sort) — the
  planner has no way to reach one user's rows or their date order without
  scanning all 6M rows. Baseline median (`baseline.py`, 1 warm-up + 5
  runs): **171.3 ms**.
- Intended fix family: a composite index on `orders (user_id, created_at
  DESC)` (or `(user_id, created_at)` — Postgres can walk a btree backward,
  so the explicit `DESC` on the second column isn't strictly required for
  correctness, only for avoiding a possible tie-break subtlety; both were
  tested and both give a plan with no `Sort` node).
- Verified in a rolled-back `BEGIN`: `CREATE INDEX idx_orders_user_created
  ON orders (user_id, created_at DESC)`. Resulting plan: `Limit` -> `Index
  Scan` on the new index directly (no `Sort`, no `Seq Scan`). Timed median
  after fix: **~0.38 ms** -> measured speedup **~453x**.
- Threshold set in `check.py`: `MIN_SPEEDUP = 50.0` (roughly 1/9 of
  measured — generous margin, since this index also has to serve tasks 02
  and 04 later on the same live DB without becoming a bottleneck itself on
  slower dev machines).
- Structural checks: forbid `Seq Scan` on `orders`; require an `Index
  Scan`-family node scoped to `table="orders"` (safe here — this query's
  `ORDER BY ... LIMIT` shape reliably produces a direct `Index Scan`, never
  a `Bitmap Heap Scan`, across every index variant tried).

## 02-support-dashboard

- Defect: (a), same root cause as task 01, different query shape.
  `queries/q02.sql` is `WHERE user_id = 42 AND created_at >= now() -
  interval '90 days'` feeding `count(*)`/`sum()`/`max()` — a range
  predicate and an aggregate, no `ORDER BY`, no `LIMIT`.
- Stock symptom (measured): `Aggregate` -> `Seq Scan` on `orders`. Baseline
  median: **178.9 ms**.
- Point of the task: the composite index built for task 01,
  `(user_id, created_at DESC)`, already satisfies this query's access
  pattern under the leftmost-prefix rule (equality on `user_id`, range on
  `created_at`) with zero new DDL. Verified this explicitly: re-ran `q02`
  against a rolled-back txn with *only* task 01's index present (no
  additional index, no `INCLUDE`) — plan becomes `Aggregate` -> `Bitmap
  Heap Scan` on `orders` -> `Bitmap Index Scan` on
  `idx_orders_user_created`. Timed median: **~1.27 ms** -> measured
  speedup **~141x**.
- **Bug found and fixed while calibrating this task's checker**: the
  planner's chosen access path here is `Bitmap Heap Scan` / `Bitmap Index
  Scan`, not a plain `Index Scan`. `plan_check.py`'s `Bitmap Index Scan`
  node never carries a `Relation Name`/`Alias` of its own (only its parent
  `Bitmap Heap Scan` does), so `require_node(plan, "Index Scan",
  table="orders")` cannot match it and spuriously fails a perfectly good
  plan. Fixed by dropping the `table=` qualifier on this one `require_node`
  call in `02-support-dashboard/tests/check.py` — safe because `forbid_node`
  is still scoped to `table="orders"` and this is a single-table query, so
  any surviving index-family node necessarily serves `orders`. Documented
  inline in the checker.
- Threshold set in `check.py`: `MIN_SPEEDUP = 30.0` (~1/5 of measured).
- README explicitly tells the learner their `src/fix.sql` may legitimately
  contain no new DDL, with reasoning instead; the checker passes on plan
  shape and timing alone regardless of whether new DDL was applied.

## 04-index-only-scan

- Defect: (a) again, plus the interaction with (f) (autovacuum disabled on
  `orders`, 621k dead tuples, never vacuumed — `last_vacuum` is null in
  `pg_stat_user_tables`). `queries/q04.sql` is `WHERE user_id = 42 AND
  created_at >= now() - interval '365 days' ORDER BY created_at DESC LIMIT
  25`, selecting only `created_at, status, total_amount`.
- Stock symptom (measured): `Limit` -> `Sort` -> `Seq Scan` (parallel).
  Baseline median: **176.4 ms**.
- Intended fix family: a covering index — `CREATE INDEX ... ON orders
  (user_id, created_at DESC) INCLUDE (status, total_amount)`. Plain
  `(user_id, created_at)` (task 01's index) gets a real `Index Scan` (no
  seq scan, no sort) but *not* `Index Only Scan`, since `status` and
  `total_amount` aren't in it — confirmed this distinction explicitly
  before writing the task.
- Verified in a rolled-back `BEGIN`: with the covering index, plan becomes
  `Limit` -> `Index Only Scan` directly. Timed median: **~0.43 ms** ->
  measured speedup **~410x**. Threshold set in `check.py`:
  `MIN_SPEEDUP = 50.0` (~1/8 of measured).
- **The pedagogical payoff, confirmed by measurement**: even with a
  correct covering index and an `Index Only Scan` node in the plan,
  `Heap Fetches` on that node is **25 — equal to every row returned**.
  Zero heap-avoidance benefit despite the right index, because no page
  touched by this scan has its visibility-map all-visible bit set (nothing
  has ever vacuumed `orders`; autovacuum is off at the table level per
  defect (f)). This reproduces reliably across statistics-target values
  and across repeated runs. `check.py` requires the `Index Only Scan` node
  and the speedup, but only *reports* `Heap Fetches` as `info` — it is not
  a pass/fail condition, per spec (running `VACUUM` is explicitly out of
  scope for the verification harness and left as the learner's own call on
  their own DB copy).
- Structural checks: `require_node(plan, "Index Only Scan", table="orders")`
  — safe to scope by table here, since (unlike `Bitmap Index Scan`) an
  `Index Only Scan` node always carries its own `Relation Name`.

## 07-planner-blindspots

- Defect: (g), `orders.status SET STATISTICS 10`, combined with the
  seed process's two-phase load (`seed/generate.py`): a mid-seed `ANALYZE`
  runs after the "old" ~5.4M rows are loaded, then a "recent" ~183-day
  batch (`STATUS_W_RECENT`, deliberately skewed away from `STATUS_W_OLD`)
  is bulk-loaded afterward with no re-`ANALYZE` and autovacuum disabled on
  `orders`, so nothing ever refreshes `pg_stats` for `status` against the
  post-load data.
- Measured distribution mismatch: global `pg_stats.most_common_freqs` for
  `status='delivered'` is 0.7782 (matches the *old*-phase weight, 0.78);
  actual current global fraction is 0.673. Restricted to the last 180
  days, `delivered` is only 0.4507 and `processing`/`pending`/`paid`/
  `shipped` are all several times their globally-estimated frequency
  (e.g. `processing`: stats say 0.0187, actual in the last 180 days is
  0.0398 — and the *recent*-phase seed weight for `processing` is 0.12,
  12x the old-phase weight of 0.02).
- `src/given_query.sql` (provided to the learner, not written by them): an
  ops "orders stuck in processing" queue —
  `orders JOIN users ON u.id = o.user_id WHERE status = 'processing' AND
  created_at >= now() - interval '30 days' ORDER BY created_at LIMIT 200`.
  Chosen specifically because the misestimate on the `orders` side
  propagates into how many times the planner expects to probe `users` on
  the inner side of a `Nested Loop`, producing a dramatic, easy-to-see
  error at that node rather than a subtle one.
- Stock symptom (measured, stable across 3 repeated runs — identical
  every time given fixed data): `EXPLAIN ANALYZE` shows `Index Scan`
  `users_pkey` with `Plan Rows = 1` but `Actual Rows = 1` at
  `Actual Loops = 16628` -> `rows_estimate_error` reports **16628.0x**,
  the worst node in the plan. Underlying cause: `Bitmap Heap Scan` on
  `orders` estimates 5 rows for the `status`+date-range filter combined
  (parallelized, so `Plan Rows=5` per worker) but actually returns
  5543 rows per worker (`Actual Loops=3` workers) — off by >3000x on its
  own. Execution time ~95-126 ms across repeated runs (already exceeds
  the stated 40 ms SLA in the given query's own header).
- Verified fix in a rolled-back `BEGIN`, tried at multiple statistics
  targets (10 — i.e. unchanged — 100, 200, 1000) combined with `ANALYZE
  orders`: all four produce an **identical** resulting plan shape. Because
  `orders.status` has only 7 distinct values, even the default/unchanged
  target of 10 is large enough for `most_common_vals` to capture all of
  them once `ANALYZE` actually re-samples the table's current contents —
  the real defect is staleness (no `ANALYZE` since the recent-phase bulk
  load with autovacuum off), not the statistics-target number itself.
  This is *not* what the task's surface framing implies (defect (g)'s
  schema comment says "low statistics target ... planner misestimates"),
  but it is what the live data actually shows, so the task and checker are
  written to accept "just `ANALYZE`" as a fully valid fix alongside
  "bump `SET STATISTICS` + `ANALYZE`" — the README frames the statistics
  target as one lever to reason about, not a hard requirement, and
  `check.py` only asserts on resulting plan quality, not on which SQL
  statements were run.
- Fixed-state plan (identical across all four target values tested):
  `Bitmap Heap Scan` estimate improves to 3442 vs. actual ~16629 (a
  residual ~4.8x, itself a big improvement from >3000x); the planner
  additionally introduces a `Memoize` node wrapping the inner
  `Index Scan` on `users_pkey` (present in the fixed state, absent in
  stock) — it only adds this node when the estimated number of times the
  inner side will be probed makes caching worthwhile. Overall worst-node
  `rows_estimate_error` on the fixed plan is **200.0x**, but that number
  comes from the `Memoize` node itself (`Plan Rows=1`, `Actual Rows=1`,
  `Actual Loops=200` — 200 being exactly the query's `LIMIT`), which is a
  structural artifact of how per-loop actual rows are reported for a
  bounded nested loop, not a genuine remaining misestimate. Execution time
  after fix: ~77-78 ms (down from ~95-126 ms; a real but modest speedup —
  this task's primary signal is estimate accuracy and plan shape, not raw
  speed, per spec).
- Threshold set in `check.py`: `MAX_ESTIMATE_ERROR = 1000.0`. Stock
  (16628x) fails it by more than an order of magnitude; every fixed
  variant tested (200x) clears it with a 5x margin. Structural check:
  `require_node(plan, "Memoize")`, present in every fixed variant tested,
  absent in stock — used as the "distinguishes the good plan" structural
  assertion the spec calls for, independent of the numeric threshold.
- No timing/`baseline.py` dependency in this task's checker, per spec —
  purely plan-shape (`rows_estimate_error` + `Memoize` presence).

## Verification method used for all four

For each task: (1) ran the unmodified `check.py` against the stock DB and
recorded the exact final `NOT PASSED:` line; (2) opened one `psycopg`
connection, `BEGIN`, applied the reference fix DDL directly (never written
into any task's `src/fix.sql`, never committed to the repo), ran
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` through that same connection, fed
the resulting dict to `plan_check.forbid_node` / `require_node` /
`rows_estimate_error` directly, confirmed all structural assertions pass,
timed the query in-transaction to calibrate the speedup threshold, then
`ROLLBACK`. All four tasks' fixes (including the task-01 index reused by
tasks 02/04) were applied together in single combined rolled-back
transactions to confirm they don't conflict or shadow one another. (3)
re-queried `pg_indexes`, `pg_attribute.attstattarget`, and
`pg_class.reloptions` for `orders` after rollback to confirm the schema is
byte-identical to stock (`idx_orders_status` + `orders_pkey` only,
`status` statistics target still 10, autovacuum reloptions unchanged).
No `baseline-local.json` was written at the module root during this work
(a scratch copy was recorded outside the repo and deleted); no throwaway
scripts were left in the repository.
