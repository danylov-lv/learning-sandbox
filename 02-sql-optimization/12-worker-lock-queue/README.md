# 12 — Worker Lock Queue

## Backstory

Payment reconciliation runs as a fleet of workers: each one claims a batch
of `pending` payments, calls the payment provider's API to confirm their
final state (simulated here as a fixed delay), and marks them
`reconciled`. Ops added more workers to clear a backlog and throughput
didn't move. `pg_stat_activity` is full of sessions stuck waiting on
locks, and workers report being idle 95% of the time even though the
backlog is enormous. Adding an 8th worker didn't get the queue drained
any faster than running just one.

This is not run against the live `payments` table directly — a support
engineer would never point an untested claim query at 5.7M rows of real
payment records. Instead, the harness builds a disposable "staging
replica" (`payments_queue_arena`), runs the whole exercise against it, and
drops it afterward. Treat it exactly like you'd treat a staging copy of
the real queue.

## What's given

- `src/harness.py` — infrastructure. Builds the arena, spawns worker
  threads, runs your `src/claim.sql` against it, measures throughput and
  lock contention, tears the arena down. You should not need to edit this
  file.
- `src/claim.sql` — the STOCK claim query. This is the starting defect,
  not a solution, and it's what you rewrite.

  **Contract**: `claim.sql` receives two named parameters from the
  harness, `%(batch_size)s` and `%(worker_id)s`. It must claim up to
  `batch_size` rows currently `status = 'pending'` in
  `payments_queue_arena`, set their `status` to `'claimed'` (and, for your
  own bookkeeping/debugging, `claimed_by = %(worker_id)s`,
  `claimed_at = now()`), and `RETURNING id` the ids it claimed. The
  harness runs this file's contents as one SQL statement per claim
  attempt, in its own transaction, and commits after your simulated
  "provider API call" delay completes (see below for why the delay is
  where it is).
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`). The arena table is built from a deterministic sample of the
  real `payments` table's rows (`ORDER BY id LIMIT n`) but is otherwise
  independent of it.

## What's required

1. Run the diagnostic demo first, with the stock `claim.sql` still in
   place:
   ```
   uv run python 12-worker-lock-queue/src/harness.py --demo
   ```
   While it's running, open a second terminal and inspect `pg_locks`
   joined against `pg_stat_activity`, and `pg_blocking_pids()`, to see
   what the workers are actually doing while they're "idle."
2. Figure out why a plain `SELECT ... ORDER BY ... LIMIT n FOR UPDATE`
   claim query causes every worker to queue up behind the same rows
   instead of working on disjoint batches in parallel.
3. Rewrite `src/claim.sql` so that concurrent workers claim disjoint
   batches without blocking on each other, while still satisfying the
   contract above exactly (same named parameters, same claimed-row
   semantics, same `RETURNING id`).
4. Think about what your fix implies for delivery guarantees: could a
   claimed row ever get claimed again if a worker crashes mid-processing?
   Is that an at-least-once or an exactly-once claim? (Not asserted by the
   checker — but you should be able to answer it.)

## Completion criteria

Run, from the module root:

```
uv run python 12-worker-lock-queue/tests/check.py
```

The checker drains a fresh copy of the arena with a single worker (as a
reference), then drains a second fresh copy with 8 concurrent workers
running your current `src/claim.sql`, and verifies:

1. **Zero duplicate claims and full coverage** — every arena row ends up
   `claimed` exactly once; no row is ever returned by more than one
   worker's claim.
2. **The 8-worker drain actually scales** — its wall time must be at most
   the 1-worker reference time divided by a fixed factor. A claim query
   that serializes all workers onto the same lock queue does not clear
   this bar; one that lets workers claim disjoint batches does.

Both checks must print `PASS`, and the final line must read `PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- Row-level locking in Postgres (`SELECT ... FOR UPDATE`) and how blocked
  transactions queue on a specific row
- `FOR UPDATE SKIP LOCKED` and the class of problems it's built for
  (work-queue claiming)
- What `ORDER BY ... LIMIT ... FOR UPDATE` actually does under the hood
  when rows are already locked by another session
- At-least-once vs. exactly-once claim semantics in a worker-queue design
- Reading `pg_locks`, `pg_stat_activity`, and `pg_blocking_pids()` to
  diagnose lock contention live

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes, including the
measured numbers behind this task's thresholds. It's there for whoever
maintains this module later, not for you mid-task — reading it now would
spoil the diagnostic work. Come back to it after you're done here if
you're curious.
