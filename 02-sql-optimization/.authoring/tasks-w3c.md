# Authoring notes: task 11 (spoilers)

Off-limits for learners before attempting the corresponding task. Read
`../seed/schema.sql`'s header comments first for the full defect list this
references by letter.

## 11-vacuum-debt

- Defect: (f), autovacuum disabled at the table level on `orders`,
  `payments`, `inventory_events`, planted via `ALTER TABLE ... SET
  (autovacuum_enabled = off, autovacuum_vacuum_scale_factor = 0.8,
  autovacuum_analyze_scale_factor = 0.8)` in `seed/schema.sql`. Supporting
  color: defect (i) (`payments.external_ref` UUID-as-text with a
  btree-under-random-insert-order index) lives on the same table but is
  not this task's subject — not touched by the checker.

- Stock symptoms, measured on the live dev container
  (`02-sql-optimization-postgres-1`, Postgres 16) via catalog queries only
  (`pg_stat_user_tables`, `pg_class.reloptions`, `pg_total_relation_size` /
  `pg_relation_size`), 2026-07-08:

  | table             | n_live_tup | n_dead_tup | dead ratio | last_vacuum | last_autovacuum | total size | heap size |
  |-------------------|-----------:|-----------:|-----------:|:------------|:-----------------|-----------:|----------:|
  | orders            |  6,000,000 |    621,060 |     0.1035 | NULL        | NULL             |     625 MB |    450 MB |
  | payments          |  5,744,064 |    481,341 |     0.0838 | NULL        | NULL             |   1,327 MB |    647 MB |
  | inventory_events  |  9,000,000 |    449,927 |     0.0500 | NULL        | NULL             |   1,058 MB |    615 MB |

  Note the task brief's approximate figures ("payments 5.74M / 599k dead")
  are close but not exact to what's live now — measured `payments` dead
  count is 481,341, not ~599k. Data drifts slightly as other concurrent
  authoring agents on this server run reads/writes against the shared DB;
  the checker is ratio-based specifically so it doesn't care about the
  exact figure, only that it's `>= 0.02` in the stock state (all three are,
  by a wide margin: 5-10x the threshold).

  `reloptions` for all three: `['autovacuum_enabled=off',
  'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']`,
  confirmed directly against `pg_class`, matching `seed/schema.sql`.

  `pgstattuple` is available (`pg_available_extensions`, version 1.5,
  ships with the `postgres:16` image's contrib) but **not installed**
  (`pg_extension` only lists `plpgsql`) on the live DB at authoring time.
  Per spec, the checker never requires or installs it — it's the learner's
  own optional diagnostic step, run on their own working copy. Not created
  on the shared DB during this authoring session either, to leave that
  decision to the learner.

- Threshold chosen: `MAX_DEAD_RATIO = 0.02` (2%), as specified in the task
  brief. All three stock ratios (0.050-0.104) clear it by 2.5x-5x; a
  single successful `VACUUM` (no `FULL` needed to hit this bar, since plain
  `VACUUM` already reclaims dead-tuple space for reuse and drives
  `n_dead_tup` towards 0) brings the ratio to effectively 0 in both the
  scratch reproduction and by direct catalog-query reasoning about what
  `VACUUM` does to `n_dead_tup`.

- Reloptions gate: the simplest defensible check specified — "reloptions
  is NULL or contains no `autovacuum_enabled=off`" — was chosen over also
  requiring the 0.8 scale factors to be gone. Rationale documented in the
  README/hints instead of enforced structurally: a learner who explicitly
  sets `autovacuum_vacuum_scale_factor` to a smaller, still-reasonable
  value (rather than fully `RESET`ting it) has still solved the actual
  problem (autovacuum re-enabled, no unbounded dead-tuple growth); gating
  on the scale factors being *exactly* absent would falsely fail a
  reasonable alternative fix. `autovacuum_enabled=off` itself has no
  legitimate alternative value that doesn't defeat the point of the task,
  so it's the one hard gate.

- Vacuum-ran gate: `last_vacuum IS NOT NULL OR last_autovacuum IS NOT
  NULL`. Deliberately an OR — a learner who runs `VACUUM` manually gets
  `last_vacuum` populated immediately; a learner who only flips
  `autovacuum_enabled` back on and waits will eventually get
  `last_autovacuum` populated instead (not necessarily by the time they
  run the checker, but the OR keeps both remediation styles valid without
  the checker needing to know which one was used).

- Heap Fetches payoff (info only, per spec): the checker runs the
  task-04-shaped query (`SELECT created_at, status, total_amount FROM
  orders WHERE user_id = 42 AND created_at >= now() - interval '365 days'
  ORDER BY created_at DESC LIMIT 25`) and, only if the resulting plan
  actually contains an `Index Only Scan` node on `orders` (i.e. only if
  task 04's covering index already exists on that DB), prints its `Heap
  Fetches` count. No covering index exists on the live DB during this
  authoring session (task 04's fix is per-learner, applied to their own
  working copy, not part of the shared stock state), so on the live DB
  this currently prints the "skipping" info line, not a Heap Fetches
  number — confirmed by direct run (see stock output below). Verified the
  actual payoff mechanism in the scratch DB instead (see below): building
  the task-04 covering index and vacuuming together in miniature does
  bring `Heap Fetches` to `0`.

## Scratch-DB verification protocol and results

`VACUUM` cannot run inside a transaction block and cannot be rolled back,
so the checker was verified end-to-end against a throwaway database on
the same server rather than the shared `sandbox` DB, per the hard rule
against ever running `VACUUM`/`VACUUM FULL`/`ANALYZE` or touching
reloptions on `sandbox`.

1. **Create**: connected as `sandbox` to db `sandbox` with `autocommit`,
   ran `DROP DATABASE IF EXISTS t11_scratch; CREATE DATABASE t11_scratch`.

2. **Build miniature stock state** in `t11_scratch`: created `orders`
   (200k rows), `payments` (150k rows), `inventory_events` (150k rows)
   with the same column shapes as `seed/schema.sql` (enough columns to
   exercise the checker's catalog queries and the task-04-shaped probe
   query; no FKs needed), populated via `generate_series` (deterministic,
   vectorized in a single `INSERT ... SELECT`, not row-by-row), applied
   the identical `ALTER TABLE ... SET (autovacuum_enabled = off,
   autovacuum_vacuum_scale_factor = 0.8, autovacuum_analyze_scale_factor =
   0.8)` reloptions to all three, then ran two full-fraction `UPDATE`s per
   table (`WHERE id % 3 = 0`, flipping a status/qty_delta column back and
   forth) to generate dead tuples with autovacuum disabled, reproducing
   the stock shape in miniature:

   | table             | n_live_tup | n_dead_tup | dead ratio | reloptions                    |
   |-------------------|-----------:|-----------:|-----------:|:-------------------------------|
   | orders            |    200,000 |    133,332 |     0.6667 | autovacuum_enabled=off (+0.8s) |
   | payments          |    150,000 |    100,000 |     0.6667 | autovacuum_enabled=off (+0.8s) |
   | inventory_events  |    150,000 |    100,000 |     0.6667 | autovacuum_enabled=off (+0.8s) |

3. **First check.py run** (`PGDATABASE=t11_scratch uv run python
   11-vacuum-debt/tests/check.py`) — failed as required, with all three
   gates failing per table (9 `FAIL` lines total) and this exact final
   line:

   ```
   NOT PASSED: orders: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); orders: never vacuumed (last_vacuum and last_autovacuum both NULL); orders: dead-tuple ratio 0.6667 >= 0.02 (n_dead=133332, n_live=200000); payments: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); payments: never vacuumed (last_vacuum and last_autovacuum both NULL); payments: dead-tuple ratio 0.6667 >= 0.02 (n_dead=100000, n_live=150000); inventory_events: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); inventory_events: never vacuumed (last_vacuum and last_autovacuum both NULL); inventory_events: dead-tuple ratio 0.6667 >= 0.02 (n_dead=100000, n_live=150000)
   ```

   exit code 1, no traceback.

4. **Applied reference remediation** in `t11_scratch` (never written into
   any task's `src/fix.sql`, never committed): for each of the three
   tables, `ALTER TABLE ... RESET (autovacuum_enabled,
   autovacuum_vacuum_scale_factor, autovacuum_analyze_scale_factor)` then
   plain `VACUUM (ANALYZE) <table>` (no `FULL` needed to clear the
   checker's gates — confirms plain `VACUUM` alone is sufficient for the
   checker's ratio-based bar, consistent with the README/hints framing
   `VACUUM FULL` as a locking tradeoff decision the learner reasons about
   per table rather than something the checker mandates). Result:

   | table             | n_live_tup | n_dead_tup | last_vacuum (set)   | reloptions |
   |-------------------|-----------:|-----------:|:---------------------|:-----------|
   | orders            |    200,000 |          0 | yes                  | NULL       |
   | payments          |    150,000 |          0 | yes                  | NULL       |
   | inventory_events  |    150,000 |          0 | yes                  | NULL       |

5. **Second check.py run**, same env override — all 9 structural gates
   `PASS`, info lines print relation sizes, final line `PASSED`, exit 0.

6. **Heap Fetches payoff, verified separately in the same scratch DB**:
   built `CREATE INDEX idx_orders_user_created ON orders (user_id,
   created_at DESC) INCLUDE (status, total_amount)` (the task-04 covering
   index shape) after the remediation above, then re-ran check.py: the
   info block now reports `orders Index Only Scan Heap Fetches: 0 (rows
   returned: 25)` — confirms the didactic payoff mechanism end-to-end: a
   correct covering index plus an actual `VACUUM` (populating the
   visibility map) together drive `Heap Fetches` to 0, whereas the index
   alone (task 04's own scope) cannot.

7. **Drop**: connected as `sandbox` to db `sandbox` with `autocommit`,
   terminated any remaining backends on `t11_scratch` via
   `pg_terminate_backend`, then `DROP DATABASE IF EXISTS t11_scratch`.
   Confirmed absence: `SELECT 1 FROM pg_database WHERE
   datname='t11_scratch'` returns no rows.

8. **Stock run against the real `sandbox` DB** (no scratch, no env
   override): failed as required. Exact final line:

   ```
   NOT PASSED: orders: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); orders: never vacuumed (last_vacuum and last_autovacuum both NULL); orders: dead-tuple ratio 0.1035 >= 0.02 (n_dead=621060, n_live=6000000); payments: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); payments: never vacuumed (last_vacuum and last_autovacuum both NULL); payments: dead-tuple ratio 0.0838 >= 0.02 (n_dead=481341, n_live=5744064); inventory_events: autovacuum still disabled (reloptions=['autovacuum_enabled=off', 'autovacuum_vacuum_scale_factor=0.8', 'autovacuum_analyze_scale_factor=0.8']); inventory_events: never vacuumed (last_vacuum and last_autovacuum both NULL); inventory_events: dead-tuple ratio 0.0500 >= 0.02 (n_dead=449927, n_live=9000000)
   ```

   The info block also printed `no Index Only Scan reached on orders for
   the task-04-shaped query (task 04 not done on this DB, or no covering
   index present) -- skipping Heap Fetches report`, confirming this path
   degrades gracefully when task 04's index doesn't exist yet.

## Verification method: confirmation the shared DB is untouched

After step 8 above, re-queried `pg_class.reloptions` and
`pg_stat_user_tables` for all three tables directly against `sandbox`:
`reloptions` for all three are byte-identical to the pre-authoring state
(`autovacuum_enabled=off` + both 0.8 scale factors present), and
`n_live_tup`/`n_dead_tup` match the numbers in the table above (within
normal drift from other concurrent authoring agents' read/write activity
on the shared server — no VACUUM, ANALYZE, or reloptions change was ever
issued against `sandbox` itself during this work). `pg_database` confirms
no `t11_scratch` database remains. No `pgstattuple` extension was created
on `sandbox`. No throwaway scripts were left in the repository; the
scratch-DB build/report/remediate/drop helper lived only in the session
scratchpad directory outside the repo and was not committed.
