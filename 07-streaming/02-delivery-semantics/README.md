# 02 -- Delivery Semantics

## Backstory

Task 01 read the log with auto-commit and never thought about what "commit"
even meant -- the client library quietly committed offsets on a timer, and
if the process died between reading a message and finishing whatever it was
supposed to do with it, you'd never know whether that message got lost or
processed twice. That's fine for exploring a log. It's not fine for a
consumer whose job is "fold every price update into a warehouse table
exactly once, or at least never miss one."

Kafka does not give you exactly-once for free. What it gives you is a
knob -- when you commit an offset relative to when you do the work -- and
three names for the three things that knob can produce:

- **At-most-once**: commit the offset, *then* do the work. If the process
  dies in between, the broker already thinks that message is consumed. On
  restart you resume past it. The message is gone. Never reprocessed, never
  recorded. Fast, and silently lossy.
- **At-least-once**: do the work, *then* commit the offset. If the process
  dies in between, the broker still thinks that message is unconsumed. On
  restart you get it again. You do the work again. A duplicate, not a gap.
  Slower to reason about (you have to tolerate redelivery), never lossy.
- **Exactly-once**: the work and the commit become one atomic unit -- either
  both happen or neither does. Kafka can't do this with a plain manual
  commit against an external system like Postgres; it needs the offset and
  the write to land in the *same* transaction (task 04) or a transactional
  producer writing back into Kafka itself (task 08). Out of scope here --
  this task is the "why you'd bother" setup for both.

This task makes you build the middle one -- at-least-once -- and proves it
by actually crashing your consumer mid-stream and checking that nothing
went missing. RabbitMQ's ack/nack/requeue model maps loosely onto this, but
a queue deletes a message once it's acked; a log doesn't forget, which is
exactly why "just resume from the last committed offset" is a coherent
recovery story here and isn't really one for a queue with no replay.

## What's given

- `src/consumer.py` -- a scaffold that connects to Postgres, creates
  `ops.t02_seen` if it doesn't exist, opens a manual-commit consumer
  (`enable.auto.commit=False`) on group `t02-consumer` subscribed to
  `s07.t02.price-updates`, and stops just short of the actual poll loop
  with a `raise NotImplementedError`. Two things are already written for
  you and are not the point of the exercise:
  - `record_seen(conn, seq)` -- the "processing" side effect: inserts the
    event's `seq` into `ops.t02_seen`. Not deduplicated on purpose --
    duplicates are the expected shape of at-least-once.
  - `_maybe_crash(processed_count)` -- a **test hook**, clearly marked in
    the source. If env var `S07_CRASH_AFTER` is set, it hard-exits the
    process (`os._exit(1)`) the instant `processed_count` reaches that
    value, skipping any pending offset commit. This simulates the crash
    window you're being graded on. Call it once per message, at the point
    in your loop where you want to observe what a real crash would do
    there. Don't rely on it doing anything other than exiting the process.
- The stack from the module README: redpanda at `localhost:19092`,
  Postgres at `localhost:54307` (db `streaming`), `harness/common.py` for
  bootstrap/topic/pg helpers.

## What's required

1. Fill in the poll loop in `src/consumer.py`. Per message: decode the
   JSON value to get `seq`, decide the order of `record_seen(conn, seq)`
   and `consumer.commit(msg)`, and place `_maybe_crash(processed)` between
   them so a crash lands where you intend it to. Read the TODO comment in
   the file -- it spells out exactly what each ordering produces on
   restart (a gap vs. a duplicate).
2. Track idle time correctly: `consumer.poll(timeout)` returning `None`
   means no new message arrived, not that the topic is exhausted. Only
   exit the loop (and the process, with code 0) once you've gone
   `IDLE_EXIT_SECONDS` with no new message.
3. Your target semantic is **at-least-once**: across an injected crash, no
   message may be permanently lost. Duplicates in `ops.t02_seen` are
   expected and fine -- the validator counts `DISTINCT seq`, not row count.
4. CLI/behavior contract the validator drives against:
   - Run with `uv run python src/consumer.py` from this task's directory.
   - Fixed consumer group id `t02-consumer`.
   - Reads `s07.t02.price-updates`, writes `seq` values into
     `ops.t02_seen`.
   - Honors `S07_CRASH_AFTER` (env, integer) exactly as `_maybe_crash`
     already implements.
   - Exits `0` once caught up (idle for `IDLE_EXIT_SECONDS`); a run killed
     by the crash hook exits nonzero, which is expected and fine.

Try it by hand before trusting the validator:

```bash
uv run python src/consumer.py                       # normal run, no crash
S07_CRASH_AFTER=500 uv run python src/consumer.py    # dies partway, rerun to resume
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Resets `s07.t02.*` topics and `ops.t02_seen`, creates
  `s07.t02.price-updates` (6 partitions).
- Produces a deterministic subset -- the first 30,000 events (`seq` 0..29999)
  from `data/events.ndjson` -- onto the topic.
- Runs your consumer once with `S07_CRASH_AFTER=8000` set. A nonzero exit
  here is expected and tolerated -- that's the crash hook firing.
- Runs your consumer again with no crash env, until it exits 0 (caught up),
  timeout ~180s.
- Asserts the set of distinct `seq` values in `ops.t02_seen` equals the
  full produced set, `{0, ..., 29999}` -- zero permanent loss. If any seq
  is missing, that's an at-most-once bug (commit placed before the write)
  and the validator says so explicitly. Total row count is also reported;
  a healthy at-least-once run has more rows than distinct seqs (some
  redelivery across the crash), which is not itself a failure.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, the consumer script is missing, the crash run somehow exits
0, either run times out, or `ops.t02_seen` ends up short of the full set.

## Estimated evenings

1

## Topics to read up on

- `enable.auto.commit` vs manual `consumer.commit()`, and what "commit" means
  on a Kafka consumer (it moves the *committed offset* for the group, not a
  broker-side ack of an individual message)
- At-most-once vs at-least-once vs exactly-once, and why Kafka's manual-commit
  API alone can only give you the first two
- The crash window: what "the process dies between step A and step B" means
  operationally, and why every consumer that does external I/O has one
- Idempotent receivers: how a consumer built for at-least-once tolerates
  redelivery without corrupting downstream state (task 04 builds on this
  directly with upsert + offset-in-the-same-transaction)
- `auto.offset.reset` and what it controls on first-ever consumption by a
  group vs. resumption after a stored commit
