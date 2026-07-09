# Authoring notes: tasks 12, 13 (spoilers)

Off-limits for learners before attempting the corresponding task. These
two tasks are not part of the 01-08 defect-letter sequence in
`../seed/schema.sql` — they exercise application-side/concurrency patterns
using disposable arenas or the live schema's existing (unfixed) shape,
not new planted schema defects.

All measurements below taken on the live dev container
(`02-sql-optimization-postgres-1`, Postgres 16, `shared_buffers=1GB`).
Numbers are machine-local and only meant to justify the calibrated
thresholds in each task's `tests/check.py` — they are not asserted as
absolutes anywhere. Another authoring session was concurrently seeding/
querying `inventory_events` on the same server; no interaction observed
with either task below (neither touches that table).

## 12-worker-lock-queue

- Not a schema defect — an application-level locking anti-pattern. The
  arena (`payments_queue_arena`, UNLOGGED, dropped at start and end of
  every harness run) is a deterministic 40,000-row sample built with
  `SELECT ... FROM payments ORDER BY id LIMIT 40000`, reset to
  `status = 'pending'` regardless of the source rows' real status.
  Building it (create + `COPY`-equivalent `INSERT ... SELECT` + one
  `(status, id)` index) measured **~0.08s**, comfortably under the ~10s
  setup budget in the spec.
- **Harness variant shipped: sleep held INSIDE the claim transaction**
  (commit happens after the simulated provider-API delay), not outside
  it. This was a deliberate deviation from the "simpler" default the task
  brief offered, and was only made after measuring both:
  - Sleep OUTSIDE the txn (commit immediately after the `UPDATE`, sleep in
    Python before the next loop iteration): stock (plain `FOR UPDATE`) and
    `SKIP LOCKED` showed **no meaningful separation** at 8 workers/40k
    rows/batch=200/sleep=20ms — stock 8-worker wall **0.77s** vs.
    `SKIP LOCKED` 8-worker wall **0.71s**, both close to the 1-worker time
    divided by ~6 already, because the claim transactions are so short
    (no work happens while the lock is held) that contention is rare even
    with plain `FOR UPDATE`. This variant does not reproduce the reported
    pathology and was rejected.
  - Sleep INSIDE the txn (same parameters): stock 8-worker wall **4.84-
    4.87s**, statistically identical to the 1-worker reference
    (**4.69-4.73s**) — i.e. **zero speedup from adding 7 more workers**,
    confirming full serialization. `SKIP LOCKED` 8-worker wall **0.73-
    0.75s** vs. its own 1-worker reference **~4.70-4.73s** — a **~6.3-6.4x**
    speedup at 8 workers (79-80% of ideal linear scaling). This is the
    variant shipped. It is also the more realistic framing: "the worker
    calls the provider before committing the claim" is a defensible thing
    a real (if naive) implementation might do, not a synthetic harness
    artifact.
- Stock symptom (measured, `--demo` mode, 8 workers): max observed
  lock-waiting sessions in `pg_stat_activity` = **7** (every worker but the
  one currently holding the lock). Fixed (`SKIP LOCKED`): max observed
  lock-waiting sessions = **0** across the full drain.
  - Per-worker claimed-count distribution is itself diagnostic: stock
    leaves most workers with **0** rows claimed for long stretches (2-3
    workers do almost all the work serially, one after another, as each
    wins the lock queue in turn); `SKIP LOCKED` gives a near-even split
    (5000 rows/worker at 8 workers/40000 rows).
- Duplicate-claim / coverage check: verified with both variants that
  `unique_claimed == 40000` and `duplicate_count == 0` — plain `FOR UPDATE`
  is still *correct* (just serialized), so this gate alone would not catch
  the defect; it exists to catch a learner's broken attempt at a fix (e.g.
  dropping row-locking entirely and racing two workers onto the same
  batch), not to distinguish stock from fixed.
- Threshold set in `check.py`: `SCALING_FACTOR = 3.0`, i.e. the 8-worker
  drain must complete in <= (1-worker time / 3). Measured 1-worker
  reference ~4.7s -> threshold ~1.57s. Stock (~4.85s) fails by ~3x over
  the threshold; `SKIP LOCKED` (~0.74s) clears it with more than 2x
  margin. This is deliberately not "~1/4 of measured speedup" (the
  house style elsewhere in this module) because the *ideal* speedup here
  is bounded by worker count (8x, not 100s of x like an index fix), so
  the margin is expressed directly as a scaling factor instead.
- Exact stock `NOT PASSED` line observed:
  ```
  NOT PASSED: 8-worker wall time 4.87s > 1.58s (1-worker 4.73s / 3.0x) -- workers are not claiming in parallel, they are queuing on the same lock
  ```
  (exact wall-time numbers vary run to run within ~4.7-4.9s for stock; the
  gate reliably fails across repeated runs since stock never approaches
  the 1.5-1.6s threshold).
- Verified the `SKIP LOCKED` variant (written to a scratch file outside
  the repo, never committed to `src/claim.sql`) clears both gates:
  zero duplicates, full coverage, ~6.3-6.4x speedup, well under threshold.

## 13-kill-the-n-plus-one

- Not a schema defect — an application-code anti-pattern layered on top of
  the existing (still partially unfixed, if the learner hasn't done tasks
  01-03 on this DB) schema. Chosen fixed user ids: **712, 758, 827**, each
  with exactly **60** orders (queried live: `SELECT user_id, count(*) FROM
  orders GROUP BY user_id HAVING count(*) BETWEEN 30 AND 60 ORDER BY count
  DESC LIMIT 10` — the dataset's overall order-count distribution is
  extremely Zipf-skewed, with the single most active synthetic user
  holding 2,624,004 orders and a long tail; 60 orders is a genuinely
  "heavy" but plausible support case, not a degenerate outlier).
- Stock `fetch_dashboard()` (1 + 2*N queries, `limit=30`): measured
  **61 queries** per call for all three users (1 orders query + 30 item
  queries + 30 payment queries), wall time **~8.2-8.3s per call**. The
  dominant cost is the 30 repeated `order_items` scans: `order_items` has
  no index leading with `order_id` in stock (defect (b), the same one
  fixed in task 03 elsewhere in this module), so each per-order item query
  is a full sequential scan of 13.8M rows; `orders` also has no `user_id`
  index yet (tasks 01/02's territory), but that only costs one scan per
  call, not 30, so it is not the dominant term here.
- Verified fix (written only to a scratch file outside the repo, never
  committed to `src/dashboard.py`): a 3-query version (1 orders query, 1
  `order_items JOIN products WHERE order_id = ANY(...)`, 1 `DISTINCT ON
  (order_id) ... payments WHERE order_id = ANY(...)`) measured **3
  queries** per call, wall time **~0.90-1.02s per call** across all three
  users — an **~8-9x** wall-time reduction, still against the same
  unindexed `order_items`/`orders` (only 3 full scans total now instead of
  61). Confirms the task's framing: the query-count fix alone is a large,
  real win even before any indexing task in this module is applied; the
  checker's timing output is therefore informational only, not gating, per
  spec.
- Threshold set in `check.py`: `MAX_QUERIES_PER_CALL = 4` (the reference
  rewrite needs exactly 3; 4 leaves headroom for a learner who splits
  items and products into two queries instead of one join). Verified
  independent of order count: the check's fixed-count assertion has no
  dependency on `LIMIT`/order count by construction (it counts
  `cur.execute()` calls, not rows).
- Parity checker (`reference_dashboard()` in `check.py`): computes the
  exact same nested structure via 3 independent set-based queries,
  compared for equality against `fetch_dashboard()`'s output. **Verified
  this also passes against the stock naive implementation** (parity
  `PASS` printed before the query-count gate fails) — this is the
  spec-required proof that the parity checker agrees with the naive
  semantics, so the *only* thing failing on stock is the query-count gate,
  not a disagreement about correct output shape.
- Exact stock `NOT PASSED` line observed:
  ```
  NOT PASSED: query count exceeds 4 per call (user 712: 61 queries, user 758: 61 queries, user 827: 61 queries) -- fetch_dashboard() is still issuing one query per order (N+1)
  ```
- Both stock-run facts recorded together in one `check.py` execution: the
  parity `PASS` line and the query-count `NOT PASSED` line appeared in the
  same run against the shipped `src/dashboard.py`, confirming both halves
  of the spec's verification requirement in a single pass.

## Verification method used for both

For each task: (1) ran the unmodified `check.py`/harness against the
stock `src/claim.sql` / `src/dashboard.py` and recorded the exact final
`NOT PASSED:` line and the measured numbers above; (2) wrote a corrected
variant (SKIP LOCKED claim query / 3-query dashboard rewrite) to a file
under the OS temp directory, never inside either task's `src/`, ran it
through the same harness/checker to confirm both gates clear with
comfortable margin, then discarded the file; (3) restored the stock
`src/claim.sql` and `src/dashboard.py` from a pre-edit backup copy and
diffed byte-for-byte against the restored version to confirm no drift.

Shared-DB state after this work, confirmed by direct query:
- `payments_queue_arena` (and the calibration-only
  `payments_queue_arena_calib`/`_calib2` scratch tables used before the
  final harness existed): all dropped; `SELECT count(*) FROM pg_tables
  WHERE tablename LIKE 'payments_queue_arena%'` returns 0.
- `payments`: row count unchanged at 5,744,047; indexes unchanged
  (`payments_pkey`, `idx_payments_order_id`, `idx_payments_external_ref`
  only).
- `orders`, `order_items`, `products`: indexes unchanged from stock
  (`orders`: `orders_pkey`, `idx_orders_status`; `order_items`:
  `order_items_pkey`, `idx_order_items_product_order`; `products`:
  `products_pkey`, `idx_products_seller_id`, `idx_products_category_id`).
- No `baseline-local.json` writes and no throwaway scripts left in the
  repository; all scratch scripts used for calibration lived outside the
  repo and were discarded.
