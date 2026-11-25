# 04 -- Exactly-Once into Postgres

## Backstory

Task 02 built an at-least-once consumer and proved it with a crash: kill
the process mid-stream, restart it, and no message is permanently lost --
duplicates are fine, gaps are not. That's the right target when
"processing" a message means recording that it happened. It's the wrong
target the moment "processing" means folding a value into a running total.

A category price-total is not a log of events -- it's a single mutable
number per category. `cnt += 1` applied twice for the same event is not a
duplicate row you can spot and dedupe later; it's just a wrong number,
indistinguishable in the table from a correct one computed from a
slightly-different corpus. Kafka's delivery guarantee doesn't change
between task 02 and this task -- it's still at-least-once, full stop, with
a plain manual-commit consumer. What has to change is what you do with a
redelivered message: task 02's `record_seen` was safe to run twice by
design; a naive `cnt += 1` is not.

The fix is the same idea RabbitMQ consumers reach for when they can't
trust "acked" to mean "definitely processed exactly once either": make the
side effect idempotent, or make the checkpoint and the side effect land in
the same atomic unit. Concretely, here, that atomic unit is a Postgres
transaction -- Kafka can't extend its own transaction into an external
system with a plain manual-commit consumer (that needs either the
transactional producer from task 08, or the trick this task teaches: do
the bookkeeping that prevents double-application *inside Postgres itself*,
where you already have real transactions).

## What's given

- `src/consumer.py` -- a scaffold that:
  - Connects to Postgres and creates `core.t04_category_totals(category
    PRIMARY KEY, cnt, price_sum)` if it doesn't exist -- `ensure_core_table`,
    already written, not the point of the exercise.
  - Opens a manual-commit consumer (`enable.auto.commit=False`) on group
    `t04-consumer` subscribed to `s07.t04.price-updates`, with the short
    session/heartbeat timeouts needed for fast crash recovery.
  - Ships `_maybe_crash(processed_count)`, a **test hook** identical in
    spirit to task 02's: if env var `S07_CRASH_AFTER` is set, hard-exits
    the process (`os._exit(1)`) the instant `processed_count` reaches that
    value. Call it once per message, after your Postgres transaction has
    committed and before you commit the Kafka offset -- that's the crash
    window this task is graded on.
  - Ships an `on_assign` callback stub, called whenever partitions are
    (re)assigned. Only needed if you pick design (b) (see below); leave it
    as a plain `consumer.assign(partitions)` for design (a).
  - Stops with `raise NotImplementedError` at the one place that matters:
    applying a single event's effect on `core.t04_category_totals`
    exactly once.
- The stack from the module README: redpanda at `localhost:19092`,
  Postgres at `localhost:54307` (db `streaming`), `harness/common.py` for
  bootstrap/topic/pg helpers.

## What's required

1. Pick one of two designs (both graded identically, by the resulting
   table, not by which you chose):
   - **(a) Idempotent dedup**: your own `ops.t04_*` table keyed on each
     event's `seq`, `INSERT ... ON CONFLICT DO NOTHING`, apply the
     category-totals delta only when that insert actually inserted a new
     row -- all in one Postgres transaction.
   - **(b) Transactional offset storage**: your own `ops.t04_*` table
     storing the last-applied Kafka offset per partition, updated in the
     SAME transaction as the category-totals delta; on startup, seek each
     assigned partition to your stored offset (via `on_assign`) instead of
     trusting the broker's committed offset.
2. Whichever you pick, create your own `ops.t04_*` table yourself
   (idempotent `CREATE TABLE IF NOT EXISTS`) -- `ensure_core_table` only
   creates the graded result table.
3. Fill in the loop body in `src/consumer.py`. Per message: one Postgres
   transaction that both decides-and-applies the delta (or skips it) and
   commits once; only then `processed += 1; _maybe_crash(processed);
   consumer.commit(msg)` -- in that order.
4. **psycopg gotcha on this build (3.3.4)**: do not use `with conn:` as a
   transaction context manager -- on this version it can close the
   connection on `__exit__`, not just end the transaction. Use an explicit
   `cur = conn.cursor()` ... `conn.commit()` instead, same as
   `ensure_core_table` already does.
5. CLI/behavior contract the validator drives against:
   - Run with `uv run python src/consumer.py` from this task's directory.
   - Fixed consumer group id `t04-consumer`.
   - Reads `s07.t04.price-updates`, maintains
     `core.t04_category_totals(category, cnt, price_sum)`.
   - Honors `S07_CRASH_AFTER` (env, integer) exactly as `_maybe_crash`
     already implements.
   - Exits `0` once caught up (idle for `IDLE_EXIT_SECONDS`); a run killed
     by the crash hook exits nonzero, which is expected and fine.
   - Safe to run repeatedly, including from a completely fresh state (no
     rows in either `core.t04_category_totals` or your `ops.t04_*` table)
     -- the validator drops the result table before every grading run and
     expects your consumer to rebuild it correctly from scratch.

Try it by hand before trusting the validator:

```bash
uv run python src/consumer.py                        # normal run, no crash
S07_CRASH_AFTER=50000 uv run python src/consumer.py   # dies partway
uv run python src/consumer.py                         # resumes and catches up
uv run python src/consumer.py                         # idle immediately, totals unchanged
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Resets `s07.t04.*` topics, creates `s07.t04.price-updates` (6
  partitions), and produces the **full** corpus (200,000 events) onto it.
- Drops `core.t04_category_totals` (and the common `ops.t04_offsets` /
  `ops.t04_seen` table names defensively) for a clean slate.
- Runs your consumer with `S07_CRASH_AFTER=50000` -- expects a nonzero
  exit (the crash hook firing), tolerated.
- Runs your consumer again with `S07_CRASH_AFTER=130000` -- same, a second
  injected crash further into the stream.
- Runs your consumer a third time with no crash env, until it exits 0
  (caught up with the topic), generous timeout (~300s).
- Asserts `core.t04_category_totals` matches `data/ground-truth.json`'s
  `per_category_totals` **exactly**: every category's `cnt` matches
  exactly, `price_sum` within `0.05`; no missing or extra categories; the
  sum of all `cnt` equals `total_events`; the sum of all `price_sum`
  matches `price_sum_all` within `0.10`.
- A `cnt` that comes out too high on any category is called out explicitly
  as double-counting from redelivered messages -- that's what happens if
  the Kafka offset commit is placed before the crash hook without the
  Postgres side being made idempotent first.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, the consumer script is missing, either crash run somehow
exits 0, any run times out, the result table never gets created, or the
totals don't match ground truth exactly.

## Estimated evenings

1-2

## Topics to read up on

- Idempotent receivers / idempotent consumers: making a side effect safe
  to apply more than once for the same logical input
- `INSERT ... ON CONFLICT DO NOTHING` / `DO UPDATE` (Postgres upsert) and
  how to read back whether a conflict actually happened
- Why Kafka's plain manual-commit API cannot give you exactly-once against
  an external system by itself, and what "the offset and the write commit
  atomically" means when the external system is the one providing the
  transaction (as opposed to task 08's transactional producer, where Kafka
  itself provides it)
- Consumer `on_assign` callbacks and manually seeking a partition to an
  application-chosen offset instead of the broker's committed offset
- Why this task's failure mode (silent aggregate drift) is harder to
  detect than task 02's (a missing row) -- and what that implies for how
  you'd monitor a real exactly-once pipeline in production
