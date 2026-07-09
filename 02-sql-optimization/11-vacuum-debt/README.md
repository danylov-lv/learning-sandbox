# 11 — Vacuum Debt

## Backstory

Disk usage on the marketplace DB keeps climbing, and nobody can point to a
feature that grew. Meanwhile, a teammate working the mobile "My orders"
ticket (task 04) built exactly the covering index the textbook says should
turn that query into a pure `Index Only Scan` — and the plan does say
`Index Only Scan` — but `Heap Fetches` never drops. Every matching row
still costs a trip to the heap, covering index or not.

Both symptoms trace back to the same decision. At some point, under
incident pressure, a previous DBA ran `ALTER TABLE ... SET
(autovacuum_enabled = off)` on the three highest-churn tables —
`orders`, `payments`, `inventory_events` — "temporarily," to stop
autovacuum from competing with a load spike for I/O. Nobody ever turned it
back on. `pg_stat_user_tables.last_vacuum` and `last_autovacuum` are both
NULL for all three tables. Dead tuples have been piling up ever since,
unbounded, and the visibility map — the thing `Index Only Scan` relies on
to skip the heap — has never been built for any of them.

Your job: quantify the damage, decide what kind of `VACUUM` each table
actually needs (plain vs. `FULL` are not interchangeable — one of them
takes a lock you may not be able to afford), write the remediation script,
and make sure this can't quietly happen again.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB). Read the comments on `orders`, `payments`,
  and `inventory_events` — the `autovacuum_enabled = off` reloptions are
  right there in the `CREATE TABLE` blocks.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `orders` has
  6.0M rows, `payments` 5.7M, `inventory_events` 9.0M — all three carry
  hundreds of thousands of dead tuples and have never been vacuumed.
- `src/fix.sql` — a scaffold with a short header comment. You write your
  maintenance script here.
- `NOTES.md` — record your before/after numbers here as you go.

## What's required

1. Quantify the damage before touching anything:
   - `pg_stat_user_tables` for `n_live_tup`, `n_dead_tup`, `last_vacuum`,
     `last_autovacuum` on the three tables.
   - `pg_class.reloptions` to confirm the disabled-autovacuum storage
     parameters.
   - Relation sizes (`pg_relation_size`, `pg_total_relation_size`) —
     how much of that size is actually reclaimable?
   - Optionally, `CREATE EXTENSION pgstattuple;` on your own working
     database and use it (`pgstattuple('orders')`, etc.) for a direct
     dead-tuple / free-space breakdown per table. This is read-only
     diagnostics — safe to install; not required for the checker.
2. For each of the three tables, decide: plain `VACUUM` or `VACUUM FULL`?
   Think about what each does to disk space, what lock each takes, and
   whether that lock is something you could get away with on a table this
   size in a system that's still taking writes. The right answer is not
   necessarily the same for all three tables.
3. Write your remediation into `src/fix.sql` and run it against your own
   working copy of the database (see "A note on verifying this yourself"
   below — running `VACUUM` cannot be undone by a rollback, unlike every
   other task in this module).
4. Reset the storage parameters so the incident-era `autovacuum_enabled =
   off` (and the widened scale factors) don't silently persist after your
   cleanup — otherwise dead tuples start climbing again on the very next
   batch of writes.
5. Record your before/after numbers (dead-tuple counts, relation sizes,
   `last_vacuum`/`last_autovacuum` timestamps) in `NOTES.md`.
6. You may touch only `orders`, `payments`, `inventory_events`. Do not run
   `VACUUM`, DDL, or DML against `products`, `order_items`, `reviews`,
   `users`, `sellers`, or `categories`.

## A note on verifying this yourself

Every other task in this module can be tried inside a `BEGIN ... ROLLBACK`
and undone for free. `VACUUM` cannot run inside a transaction block and
cannot be rolled back. Before you run anything for real, think about
whether you want to try your script on a throwaway copy first (a second
local database, or a scratch schema you populate yourself) rather than
directly on the one true `sandbox` database this whole module shares with
every other task. That decision is yours to make, not the checker's.

## Completion criteria

Run, from the module root:

```
uv run python 11-vacuum-debt/tests/check.py
```

The checker verifies, for each of `orders`, `payments`, `inventory_events`:

1. `pg_class.reloptions` no longer contains `autovacuum_enabled=off`.
2. `pg_stat_user_tables.last_vacuum` or `last_autovacuum` is not NULL —
   something has actually vacuumed the table.
3. The dead-tuple ratio (`n_dead_tup / n_live_tup`) is below a small
   threshold — this is a ratio, not a row-count check, so it holds
   regardless of how much the table has grown since these numbers were
   measured.

It also prints, purely as information (not pass/fail): relation sizes for
all three tables, and — only if a covering index from task 04 already
makes `orders` reachable via `Index Only Scan` — the `Heap Fetches` count
for the task-04-shaped query. If you've done task 04 and then vacuum
`orders` here, watch that number: it is the payoff of this task.

All required checks must print `PASS`, and the final line must read
`PASSED`.

## Estimated evenings

1

## Topics to read up on

- `VACUUM` vs. `VACUUM FULL` — what each reclaims, and what lock each takes
- `autovacuum_vacuum_scale_factor` / `autovacuum_analyze_scale_factor` and
  how they interact with table size
- `pg_stat_user_tables`: `n_live_tup`, `n_dead_tup`, `last_vacuum`,
  `last_autovacuum`, `last_analyze`, `last_autoanalyze`
- The visibility map and its relationship to `Index Only Scan`
- `pgstattuple` and what it measures that the catalog stats don't
- `ALTER TABLE ... SET` / `RESET` for storage parameters (`reloptions`)

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes. It's there for
whoever maintains this module later, not for you mid-task — reading it now
would spoil the diagnostic work. Come back to it after you're done here if
you're curious.
