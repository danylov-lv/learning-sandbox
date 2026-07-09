# Authoring notes: tasks 09, 10 (spoilers)

Off-limits for learners before attempting the corresponding task. Read
`../seed/schema.sql`'s header comments first for the full defect list this
references by letter.

All measurements below taken on the live dev container
(`02-sql-optimization-postgres-1`, Postgres 16, `shared_buffers=1GB`,
`inventory_events` 9.0M rows / 450k dead tuples, `min(occurred_at)` =
2025-01-10 07:21:23, `max(occurred_at)` = 2026-07-08 11:59:59). Numbers are
machine-local and only meant to justify the calibrated thresholds in each
task's `tests/check.py` — they are not asserted as absolutes anywhere.
Both tasks target `inventory_events` exclusively, which no other
concurrently-running authoring agent touches.

## 09-deep-pagination

- Defect: (c)'s query-shape half — `inventory_events` has a single-column
  index on `occurred_at` (and one on `product_id`), nothing composite. Deep
  `OFFSET` pagination on `ORDER BY occurred_at DESC, id DESC` cannot be
  served by seeking; the executor has to produce every row up to the
  offset and discard it.
- Given query tuning: the spec sketch suggested `OFFSET 150000`, but at
  that offset the stock median was only ~28.5 ms — too fast to be a
  believable "the endpoint times out" story and too close to noise for a
  robust speedup measurement. Tuned upward: `OFFSET 300000` -> 55.9 ms,
  `OFFSET 500000` -> 87.4 ms, `OFFSET 800000` -> **151.7–188.4 ms across
  repeated 5-run medians** (chosen), `OFFSET 1200000` -> 280.1 ms. Settled
  on `OFFSET 800000 LIMIT 100` as the given query — comfortably over the
  spec's "> = 100 ms" bar with margin, without needing an implausibly deep
  page.
- Stock plan for the given query: `Limit` -> `Incremental Sort` (`Sort
  Key: occurred_at DESC, id DESC`, `Presorted Key: occurred_at`) ->
  `Index Scan` (Backward) on `idx_inventory_events_occurred_at`. The
  `Incremental Sort` exists because of the `id DESC` tie-break — plain
  `occurred_at` ordering from the index isn't quite the full sort key,
  since many rows share a timestamp (`Full-sort Groups: 24689` observed
  for a run producing ~800,100 rows). The index scan itself reports
  `Actual Rows` in the 800,000+ range — it really did walk (and the sort
  step really did process) everything up to the offset.
- Intended fix family: keyset pagination — `WHERE (occurred_at, id) <
  (%(cursor_occurred_at)s, %(cursor_id)s) ORDER BY occurred_at DESC, id
  DESC LIMIT 100`, using Postgres's row-value comparison so the tie-break
  is handled correctly at the predicate level, not just in `ORDER BY`.
- **Verified in a rolled-back `BEGIN`, two variants, per the spec's request
  to check whether the rewrite alone suffices**:
  - Rewrite alone (no new index, only the existing single-column
    `idx_inventory_events_occurred_at`): plan is `Limit` -> `Incremental
    Sort` -> `Index Scan` (Forward) on the existing index, with `Index
    Cond: (occurred_at <= cursor)` pushed down and the row-value predicate
    applied as a residual `Filter`. Actual Rows on the Index Scan node:
    **101** (i.e. it stops almost immediately once past the cursor — the
    `Filter` only discards a handful of rows sharing the boundary
    timestamp, not the 800,000 before it). Timed median: **0.7–0.8 ms**
    across 4 repeated 5-run comparisons -> speedup **230x–255x**.
  - With an added composite index `(occurred_at DESC, id DESC)`: plan
    collapses to `Limit` -> `Index Scan` (Forward) directly on the new
    index, `Index Cond` is the full row-value comparison, no `Incremental
    Sort` node at all, Actual Rows exactly **100** (no filter residual).
    Timed: **~0.07 ms** in-transaction — even faster, and structurally
    cleaner (no sort step at any offset depth).
  - **Conclusion, as instructed to document either way**: the rewrite
    alone already fixes the pathology completely (from ~800,000-row index
    walk + full incremental sort, down to a ~101-row index probe) — a
    single-column B-tree on the leading sort column is enough for Postgres
    to push the first-column bound down as an `Index Cond` and do the
    tie-break as a cheap in-memory filter over a tiny row set. The
    composite index is a genuine, measurable improvement on top (no sort
    node, no filter residual, ~10x tighter timing) but is not required to
    clear this task's thresholds. `src/fix.sql` therefore legitimately may
    contain nothing; `README.md` and `hint-3.md` say this explicitly.
- Threshold set in `check.py`: `MIN_SPEEDUP = 30.0` — roughly 1/8 of the
  weaker (rewrite-only) measured speedup (~230-255x), a larger-than-usual
  margin because this comparison has two independent sources of noise
  (0.7-0.8 ms measurements are close to per-connection/per-round-trip
  overhead, and the 141-188 ms baseline itself varied by ~30% across
  recording runs under shared-server load).
- Structural check: `Index Scan`-family node on `inventory_events` with
  `Actual Rows <= 1000` (chosen well above the ~100-101 rows seen in both
  verified variants, comfortable margin for a learner's slightly different
  but still-correct predicate shape).
- Baseline recorded: `given_query_09` -> median **141.2 ms** (1 warm-up +
  5 runs: 141.2, 145.6, 164.3, 140.9, 139.8 — slightly lower than the
  151.7-188.4 ms range seen during offset tuning, consistent with normal
  shared-server variance; still comfortably above the 100 ms design bar).
- End-to-end dry run of the real checker (not just the underlying
  queries): temporarily wrote the row-value rewrite into
  `src/page_query.sql`, ran `tests/check.py` for real, got all four `PASS`
  lines and `PASSED`, then reverted `page_query.sql` back to the shipped
  `WHERE false` stub before finishing. No reference SQL was left in the
  repository at any point after this check.

## 10-partition-the-firehose

- Defect: (c)'s retention half — `inventory_events` is a single 9.0M-row
  unpartitioned heap; `autovacuum_enabled = off` at the table level means
  past monthly retention `DELETE`s already left 450k dead tuples with
  nothing to reclaim them.
- Live data span, queried directly before writing anything: `count(*) =
  9,000,000`, `min(occurred_at) = 2025-01-10 07:21:23`, `max(occurred_at)
  = 2026-07-08 11:59:59`, `sum(qty_delta) = 183,651,745`. Per-month counts
  (`date_trunc('month', occurred_at)`) confirmed a clean ramp from 492
  rows in Jan 2025 to 1.43M in Jun 2026 and a partial 400,614 in Jul 2026
  (the in-progress month) — 19 calendar months of real data (Jan 2025
  through Jul 2026 inclusive).
- Intended fix family: copy-and-swap migration inside one transaction —
  build a new table `PARTITION BY RANGE (occurred_at)` with one partition
  per calendar month covering Jan 2025 through at least one month past the
  data's max (verified with partitions through Sep 2026, i.e. 21 total: 19
  months of real data + 2 wholly-future months), `INSERT ... SELECT` all
  rows across, rename-swap into `inventory_events`, recreate the two
  useful indexes (`occurred_at`, `product_id`) directly on the partitioned
  parent so they propagate to every partition (present and future).
- **Verified in a rolled-back `BEGIN`** (full script: create partitioned
  shadow table + 21 monthly partitions, `INSERT ... SELECT`, rename swap,
  recreate both indexes, run every one of `check.py`'s assertions through
  that same connection/cursor, then `ROLLBACK`):
  - Partition creation: negligible (<0.1s for 21 `CREATE TABLE ...
    PARTITION OF` statements).
  - `INSERT ... SELECT` of all 9,000,000 rows: **7.0–8.5 s** across two
    runs.
  - Recreating both indexes on the now-partitioned table (21 partitions
    each): **4.5–6.6 s**.
  - Total migration time in-transaction: comfortably under 20 s at this
    row count — well within the "a few minutes is fine" allowance, so no
    special-casing needed for a long-running transaction in the checker.
  - Post-migration parity, queried through the same transaction:
    `count(*) = 9,000,000`, `sum(qty_delta) = 183,651,745`,
    `min(occurred_at)` / `max(occurred_at)` byte-identical to the
    pre-migration values above. Exact match, as expected for a straight
    `INSERT ... SELECT`.
  - `pg_partitioned_table` / `pg_class` join confirms `partstrat = 'r'`
    (RANGE) once the swap is done and the table is named
    `inventory_events` again.
  - Partition-bound introspection via `pg_get_expr(c.relpartbound, c.oid)`
    on `pg_inherits` children, regex-extracting the first quoted timestamp
    as the lower bound: correctly identifies the Aug/Sep 2026 partitions
    as strictly after the stock `max(occurred_at)` (2026-07-08).
- **Pruning query shape, an important calibration finding**: the spec's
  suggested recent-window shape (`occurred_at >= now() - interval '14
  days'`, open-ended, no upper bound) does **not** prune to <= 2
  partitions — it prunes to **4** (Jun, Jul, Aug, Sep 2026), because an
  unbounded-above range is structurally satisfied by every partition whose
  upper bound exceeds the cutoff, which includes every future partition
  created for retention headroom, not just the ones with actual matching
  data. This reproduced identically with plain `EXPLAIN` and with
  `EXPLAIN ANALYZE` (real per-statement pruning, not just a planner
  artifact). Adding a matching upper bound —
  `occurred_at >= now() - interval '14 days' AND occurred_at <= now()` —
  prunes cleanly to the **2** partitions that actually straddle the
  window (Jun + Jul 2026, since the 14-day lookback from Jul 8 crosses the
  month boundary), both with and without `ANALYZE`. `check.py` and
  `src/recent_window_query.sql` use the bounded form; `MAX_SCANNED_
  PARTITIONS = 2` is set against this measurement, not the spec's
  unqualified suggestion, and this decision is documented in `check.py`'s
  own docstring plus here.
- Timing, informational only per spec's explicit option to skip a hard
  gate: stock baseline (`recent_window_stock`, bounded query, 1 warm-up +
  5 runs) -> median **141.0 ms** (range 137.0-182.7 ms, i.e. quite noisy
  under shared load). Partitioned (in-transaction, 1 warm-up + 5 runs) ->
  median **96.4 ms** (range 93.5-109.2 ms). Speedup **~1.5x** — real but
  modest, because the stock table already has a B-tree on `occurred_at`
  and gets an `Index Only Scan` for this query; partitioning mainly
  changes how much of that index has to be consulted (2 small partition
  indexes instead of 1 big one), not whether an index is used at all.
  **Decision**: given the modest magnitude and the noise band overlapping
  a plausible ~1.0-1.3x on a slower run, a hard `MIN_SPEEDUP` gate here
  would be fragile; `check.py` prints this comparison as `info` only and
  gates purely on partitioning structure, parity, and pruning — the
  README says so explicitly and explains why.
- Threshold set in `check.py`: `MIN_PARTITIONS = 20` (19 months of real
  data + >= 1 future month, matches the 21 verified). No `MIN_SPEEDUP`
  (see above).
- Stock `NOT PASSED` line (module unmodified): `inventory_events is not a
  partitioned table -- apply src/migrate.sql against the live database
  first`.
- Verified the full `check.py` assertion sequence (partstrat, partition
  count, future-bound detection, parity, pruning) by calling the exact
  same SQL the checker runs, through the same open, uncommitted
  transaction as the reference migration, before rolling back — see
  `migrate_verify_full.py` results: all four structural checks reported
  PASS in-transaction. `check.py` itself was only ever run against the
  live, unmodified stock DB (never against a committed migrated schema) —
  it correctly fails clean before any migration is applied, and the repo
  was never left with a partitioned `inventory_events`.

## Verification method used for both

For each task: (1) ran the unmodified `check.py` against the stock DB and
recorded the exact final `NOT PASSED:` line; (2) opened one `psycopg`
connection, `BEGIN`, applied the reference fix (a keyset predicate for 09,
tested with and without a supporting composite index; a full copy-and-swap
partitioning migration for 10) directly against that connection — never
written into any task's shipped `src/` files, never committed to the
repo — ran `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` / the checker's exact
structural queries through that same connection, confirmed everything
`check.py` asserts actually holds, timed the query in-transaction to
calibrate speedup/threshold decisions, then `ROLLBACK`. For task 09, the
reference rewrite was also dropped into the shipped `src/page_query.sql`
temporarily, `tests/check.py` was run for real end-to-end (all four `PASS`
lines, final `PASSED`), and the stub was restored immediately afterward —
no reference SQL remains in the repository. For task 10, `check.py`'s
assertion queries were replicated line-for-line against the same
uncommitted transaction as the reference migration rather than run as a
separate process, since committing the migration (even briefly) to run
`check.py` as an external process would have violated the "never commit
DDL to this DB" rule. After each task's verification, re-queried
`pg_indexes` and `pg_class` (`relkind`, `reloptions`) for
`inventory_events` to confirm the schema is byte-identical to stock: three
indexes (`inventory_events_pkey`, `idx_inventory_events_product_id`,
`idx_inventory_events_occurred_at`), ordinary heap table (`relkind = 'r'`,
not partitioned), `autovacuum_enabled=off` /
`autovacuum_vacuum_scale_factor=0.8` /
`autovacuum_analyze_scale_factor=0.8` reloptions unchanged, row count
still 9,000,000. Confirmed after task 09's work and again after task 10's
work. `baseline-local.json` at the module root now contains entries for
`deep_page_800k` (a discarded tuning id), `given_query_09`, and
`recent_window_stock` — all machine-local and gitignored; no throwaway
scripts were left in the repository (temporary Python experiment files
used for this calibration lived under the session scratch directory,
outside the repo, and were not copied in).
