# 05 -- Replica Lag and Alerting

## Backstory

In the RabbitMQ world, "is my consumer behind" is a queue-depth question --
the broker keeps a live count of unacked messages sitting in the queue and
tells you, no computation required. CDC through Debezium doesn't have that
single number, and it doesn't have just one *kind* of behind either.

There are two independent systems here, each with its own notion of lag:

1. Kafka doesn't drop a message once a consumer reads it, so "is the
   materializer keeping up with `s08.t05.shop.offers`" is the same
   high-watermark-minus-committed-offset question you already answered in
   module 07 -- consumer-group lag, the primary signal.
2. But upstream of Kafka there's a second, quieter failure mode a queue
   simply has no equivalent of: the Postgres replication *slot* Debezium
   reads from pins write-ahead log on the source until the slot confirms
   it has flushed past a given point. If Debezium (or Kafka Connect's own
   offset-commit cycle) falls behind, the source keeps retaining WAL bytes
   it would otherwise recycle -- disk fills up on a machine nobody's
   watching, for a reason that never shows up in any consumer's lag number.

A CDC replica silently falling behind is worse than a loud failure --
dashboards downstream keep reading stale data while believing it's fresh.
This task builds the monitor that catches both failure modes: it quantifies
lag two ways and raises an alert once the primary one crosses a threshold.

## What's given

- `src/monitor.py` -- a scaffold that:
  - Connects to the mart and creates `ops.t05_lag_snapshots` if it doesn't
    exist yet (`ensure_ops_table`, already written).
  - Fixes `TOPIC = "s08.t05.shop.offers"`, `GROUP_ID = "t05-materializer"`,
    `SLOT_NAME = "s08_t05_slot"`.
  - Reads the alert threshold from env var `S08_LAG_THRESHOLD` (default
    `1000`) via `lag_threshold()`, already written.
  - Stops with `raise NotImplementedError` at the one place that matters:
    computing both lag numbers, deciding the alert, and persisting a row.
- The stack from the module README: source Postgres at `localhost:54308`,
  mart Postgres at `localhost:54318`, redpanda at `localhost:19093`, Kafka
  Connect REST at `localhost:8383`.
- `harness/common.py` -- in particular `consumer_lag(group, topic)` (total
  lag across partitions, already implemented -- this task does not ask you
  to re-derive it), `source_current_lsn(conn)`, `replication_slots(conn)`,
  `mart_connect()`, `source_connect()`.

## What's required

Fill in `main()` in `src/monitor.py`. Per invocation (the script takes
**exactly one snapshot and exits** -- it is not a poll loop):

1. **Consumer lag** -- call `consumer_lag(GROUP_ID, TOPIC)` for the total
   count of change events on the topic the materializer group has not yet
   committed. This is the primary, deterministic signal: it doesn't depend
   on anything actually reading the topic, only on broker metadata (high
   watermark vs. committed offset).
2. **Slot lag bytes** -- how far behind the source's replication slot
   `SLOT_NAME` is, in bytes: the gap between the source's current WAL
   position and the slot's `confirmed_flush_lsn`. `source_current_lsn(conn)`
   gives you the first LSN; `replication_slots(conn)` gives you a row per
   slot including `confirmed_flush_lsn` -- note its own `lag_bytes` column
   is computed against `restart_lsn`, a related but different number (see
   Topics below), so for this task you compute the confirmed-flush-based
   gap yourself, via the same SQL function Postgres itself uses for LSN
   arithmetic.
3. **Alert** -- `alert = consumer_lag > lag_threshold()` (strictly greater).
4. Write one row into `ops.t05_lag_snapshots(consumer_lag, slot_lag_bytes,
   alert)` and commit. Safe to run repeatedly -- every run appends a new
   row, never overwrites a previous one.

psycopg gotcha on this build (3.x): do not use `with conn:` as a transaction
context manager -- it can close the connection on `__exit__`, not just end
the transaction. Use an explicit cursor + `conn.commit()`.

Try it by hand once you have a connector running (the validator sets one up
for you, named `s08-t05`, but you can register your own with a different
name to poke at this independently):

```bash
uv run python src/monitor.py                       # one snapshot, exits 0
S08_LAG_THRESHOLD=10 uv run python src/monitor.py   # lower threshold, more likely to alert
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

1. Tears down any leftover `s08-t05` connector/slot/publication/topics and
   drops `ops.t05_lag_snapshots` for a clean slate.
2. Confirms the source is seeded against `data/ground-truth.json` (tells
   you to run `uv run python generate.py` if not).
3. Registers connector `s08-t05` (twice, to prove your config is idempotent
   to re-register) and waits for it to reach `RUNNING`.
4. **Phase 1 (caught up)**: waits for the snapshot phase to fully land on
   `s08.t05.shop.offers`, then commits the `t05-materializer` group's
   offsets to exactly the resulting high watermark -- without consuming a
   single message, so lag is provably zero by construction. Runs your
   monitor once; asserts the newest row has `consumer_lag=0` and
   `alert=FALSE`.
5. **Phase 2 (fallen behind)**: applies a deterministic burst (1200
   inserts, 1500 updates, 300 deletes -- 3300 Kafka messages once you count
   the tombstone that follows each delete) directly against the source and
   waits for it to stream onto the topic, but never advances the
   materializer group's committed offsets. Runs your monitor again; asserts
   the newest row has `consumer_lag >= 1000`, `alert=TRUE`, and
   `slot_lag_bytes > 0`.
6. Tears everything down, drops the snapshots table, and reseeds the
   source, leaving the stack clean for the next task.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack
is down, the source isn't seeded, `src/monitor.py` errors out or times out,
the table never gets created, or either phase's numbers don't match what
the validator independently computes from broker/source metadata.

## Estimated evenings

1

## Topics to read up on

- Consumer-group lag: high watermark vs. committed offset (same mechanism
  as module 07, now measuring a Debezium topic instead of an application
  event stream)
- Replication-slot lag and WAL retention: why an inactive or slow slot
  makes Postgres hold onto WAL segments it would otherwise recycle
- `confirmed_flush_lsn` vs. `restart_lsn` in `pg_replication_slots` -- two
  different "how far behind" answers from the same slot
- Alerting thresholds and staleness: why the interesting question is
  usually "how long has it been over threshold," not just "is it over
  threshold right now"
- Why an unmonitored replication slot is an operational hazard (disk usage
  with no consumer-side symptom until it's already a problem)
