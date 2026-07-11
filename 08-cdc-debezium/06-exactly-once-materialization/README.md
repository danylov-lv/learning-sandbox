# 06 -- Exactly-Once Materialization

## Backstory

Task 03 built an idempotent upsert of `shop.offers` change events into
`replica.offers` and got exactly-once behavior almost for free: replaying
the same `after` image twice is a no-op, and deleting an already-deleted row
is a no-op too. At-least-once delivery stopped being a problem the moment
the side effect itself stopped caring how many times it ran.

Now add one more thing next to that upsert: a running count of how many
change events you've applied per offer -- or, simpler, a single
`applied_changes` counter for the whole mart. The upsert is still safe to
redeliver. The counter is not. `applied_changes += 1` run twice for the same
event is a silent over-count, invisible in the table the same way 07/04's
`cnt += 1` was: there's no row you can point to and call a duplicate, just a
number that's wrong forever.

The failure mode is exactly 07/04's: a consumer crashes AFTER its mart
transaction commits but BEFORE it commits the Kafka offset. On restart, that
same event is redelivered. The upsert half shrugs it off. The counter half
does not, unless you make "apply this change to the mart" and "remember I
applied it" the same atomic Postgres transaction -- committed before the
Kafka offset commit is ever attempted. This is the CDC analogue of 07/04:
same crash window, same fix, this time driven by a Debezium change stream
instead of an application-level event topic.

## What's given

- `src/materialize.py` -- a scaffold that:
  - Opens a mart Postgres connection and creates
    `replica.offers(offer_id PRIMARY KEY, product_id, seller, price,
    currency, in_stock, updated_at)` and `mart.t06_meta(id, applied_changes)`
    (seeded with one row, `applied_changes = 0`) if they don't exist --
    `ensure_mart_tables`, already written, not the point of the exercise.
  - Opens a manual-commit consumer on group `t06-materializer`, subscribed
    to `s08.t06.shop.offers`.
  - Ships `_maybe_crash(processed_count)`, a **test hook** identical in
    spirit to 07/04's: if env var `S08_CRASH_AFTER` is set, hard-exits the
    process (`os._exit(1)`) the instant `processed_count` reaches that
    value. Call it once per message, after your mart transaction has
    committed and before you commit the Kafka offset -- that's the crash
    window this task is graded on.
  - Ships an `on_assign` callback stub, only needed if you pick design (b)
    (see below); leave it as a plain `consumer.assign(partitions)` for
    design (a).
  - Runs an idle-exit loop: after `IDLE_EXIT_SECONDS` (~10s) with no new
    message, it commits offsets, closes cleanly, and exits `0`.
  - Decodes each message with `harness.common.decode_value` / `change_op`,
    skipping tombstones before your code runs.
  - Stops with `raise NotImplementedError` at the one place that matters:
    applying a single change event to the mart -- both halves -- exactly
    once.
- The stack from the module README: source Postgres at `localhost:54308`
  (db `shop`), mart Postgres at `localhost:54318` (db `mart`), redpanda at
  `localhost:19093`, Kafka Connect REST at `localhost:8383`,
  `harness/common.py` for connection/topic/connector helpers.
- The validator registers your connector for you (name `s08-t06`, slot
  `s08_t06_slot`, publication `s08_t06_pub`, `topic.prefix` `s08.t06` ->
  topic `s08.t06.shop.offers`, `decimal.handling.mode=double` so prices
  arrive as plain JSON numbers) -- you are not writing connector
  registration code in this task, only the consumer.

## What's required

1. Pick one of two designs (both graded identically, by the resulting
   tables, not by which you chose):
   - **(a) Idempotent dedup**: your own `ops.t06_*` table keyed on each
     event's identity -- either the Kafka `(partition, offset)` pair or the
     Debezium `source.lsn` field from the decoded payload -- `INSERT ...
     ON CONFLICT DO NOTHING`, apply the replica write AND the
     `applied_changes` increment only when that insert actually inserted a
     new row -- all in one Postgres transaction.
   - **(b) Transactional offset storage**: your own `ops.t06_*` table
     storing the last-applied Kafka offset per partition, updated in the
     SAME transaction as the replica write and the `applied_changes`
     increment; on startup, seek each assigned partition to your stored
     offset (via `on_assign`) instead of trusting the broker's committed
     offset.
2. Whichever you pick, create your own `ops.t06_*` table yourself
   (idempotent `CREATE TABLE IF NOT EXISTS`) -- `ensure_mart_tables` only
   creates the graded result tables.
3. Fill in `apply_change` in `src/materialize.py`. Per non-tombstone event,
   one Postgres transaction that: dedups (or checks the offset), then (if
   not already applied) upserts/deletes `replica.offers` from
   `before`/`after` AND increments `mart.t06_meta.applied_changes` by 1,
   then commits once. Tombstones are already filtered out before your code
   runs -- they never touch `applied_changes`.
4. **psycopg gotcha**: do not use `with conn:` as a transaction context
   manager -- on this build it can close the connection on `__exit__`, not
   just end the transaction. Use an explicit `cur = conn.cursor()` ...
   `conn.commit()` instead, same as `ensure_mart_tables` already does.
5. CLI/behavior contract the validator drives against:
   - Run with `uv run python src/materialize.py` from this task's
     directory.
   - Fixed consumer group id `t06-materializer`.
   - Reads `s08.t06.shop.offers` from the beginning, maintains
     `replica.offers` and `mart.t06_meta`.
   - Honors `S08_CRASH_AFTER` (env, integer) exactly as `_maybe_crash`
     already implements.
   - Exits `0` once caught up (idle for `IDLE_EXIT_SECONDS`); a run killed
     by the crash hook exits nonzero, which is expected and fine.
   - Safe to run repeatedly, including from a completely fresh state -- the
     validator drops both result tables before every grading run.

Try it by hand before trusting the validator:

```bash
uv run python src/materialize.py                        # normal run, no crash
S08_CRASH_AFTER=8000 uv run python src/materialize.py    # dies partway
uv run python src/materialize.py                         # resumes and catches up
uv run python src/materialize.py                         # idle immediately, counter unchanged
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Clean-slates task 06's connector, slot, publication, topic, and drops
  `replica.offers`, `mart.t06_meta`, and defensively `ops.t06_seen` /
  `ops.t06_offsets`.
- Ensures the source is seeded (`NOT PASSED` telling you to run
  `generate.py` if not).
- Registers the `s08-t06` connector and waits for its snapshot to finish.
- Applies a deterministic burst (800 inserts, 1500 updates, 400 deletes) to
  `shop.offers` and waits for the change stream to fully catch up.
- Runs your `materialize.py` with `S08_CRASH_AFTER=8000` -- expects a
  nonzero exit (the crash hook firing).
- Runs it again with `S08_CRASH_AFTER=18000` -- same, a second injected
  crash further into the stream.
- Runs it a third time with no crash env, until it exits 0 (caught up),
  generous timeout (~300s).
- Independently drains the topic and counts every non-tombstone event
  (`op` in `r`, `c`, `u`, `d`) -- call this `EXPECTED`.
- Asserts `replica.offers` matches the live `shop.offers` EXACTLY (same
  offer_ids, matching `product_id`/`seller`/`currency`/`in_stock`, `price`
  within `0.01`).
- Asserts `mart.t06_meta.applied_changes` equals `EXPECTED` EXACTLY. A
  value ABOVE `EXPECTED` is called out explicitly as double-counting from
  redelivery across one of the injected crashes.
- Tears everything down afterward and restores the source to its stock
  seed.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack
is down, `src/materialize.py` is missing, either crash run somehow exits 0,
any run times out, the result tables never get created, or either check
above doesn't match exactly.

## Estimated evenings

1-2

## Topics to read up on

- Idempotent vs. exactly-once side effects: why an upsert is idempotent for
  free but a running counter is not
- Dedup key choice: Kafka `(partition, offset)` vs. the Debezium
  `source.lsn` field
- Transactional outbox/inbox pattern
- The redelivery window: work committed, checkpoint not yet committed
- Monitoring for silent aggregate drift in a materialized view fed by CDC
