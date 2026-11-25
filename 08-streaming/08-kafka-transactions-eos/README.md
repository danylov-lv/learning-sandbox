# 08 -- Kafka Transactions and Exactly-Once (Topic-to-Topic)

## Backstory

Task 04 solved exactly-once the RabbitMQ way: Kafka stayed at-least-once,
full stop, and the trick was making the *external system* (Postgres) the
place where "did the work" and "remember I did it" land atomically. That
works because Postgres has real transactions and you control the schema.
It does not help at all when the "external system" your consumer writes
to is *another Kafka topic* -- there's no foreign database to smuggle an
offset into. If you read from `s07.t08.price-updates`, transform each
event, and produce it to `s07.t08.enriched`, a plain manual-commit
consumer plus a plain producer gives you the same at-least-once gap as
always: crash after producing the transformed record but before
committing the input offset, and the record gets produced again on
redelivery. Downstream, that's a duplicate with no dedup table to catch
it.

Kafka has its own answer to this, and it's the one task 04's README
pointed forward to: a **transactional producer**. A producer with a fixed
`transactional.id` can atomically bundle "records I produced" and "input
offsets I consumed" into a single Kafka transaction, via
`send_offsets_to_transaction`. Either the whole batch -- the produced
output records AND the consumer offset advance -- becomes visible
together, or (on a crash or abort) none of it does. A downstream consumer
reading with `isolation.level=read_committed` never sees the output side
of an aborted transaction at all; it's as if those records were never
produced. This is Kafka providing the transaction itself, rather than
you borrowing one from Postgres.

## What's given

- `src/processor.py` -- a scaffold that:
  - Defines the fixed identifiers the validator drives against: input
    topic `s07.t08.price-updates`, output topic `s07.t08.enriched`,
    consumer group `t08-processor`, producer `transactional.id`
    `s07-t08-eos`, and `BATCH_SIZE = 5000`.
  - Opens a manual-commit consumer (`enable.auto.commit=False`,
    `auto.offset.reset='earliest'`, short session timeout for fast crash
    recovery) and a transactional producer (fixed `transactional.id` --
    needed so a restarted process fences off any "zombie" instance of
    itself still holding the previous transaction).
  - Ships `_maybe_crash(processed_count)`, a **test hook** identical in
    spirit to task 04's: if env var `S07_CRASH_AFTER` is set, hard-exits
    the process (`os._exit(1)`) the instant `processed_count` reaches
    that value. You must call it from INSIDE an open transaction --
    after producing some of the current batch's output records, before
    `commit_transaction()` -- so the crash actually aborts a
    transaction-in-flight rather than landing between batches.
  - Stops with `raise NotImplementedError` at the transaction body:
    `init_transactions()` once, then per batch: `begin_transaction()`,
    produce the transformed records, `send_offsets_to_transaction(...)`,
    `commit_transaction()` (with `abort_transaction()` on error).
  - An idle-exit loop: exits `0` once it has gone quiet with no new
    input for a while (caught up with the topic).

## What's required

1. Fill in `main()` in `src/processor.py`:
   - `init_transactions()` **once**, before the consume loop starts --
     not per batch. This is what performs the zombie-fencing handshake:
     if a previous instance of this same `transactional.id` is still
     mid-transaction somewhere (e.g. the process this one is replacing
     after a crash), the broker bumps the producer epoch and any
     leftover transaction from the old instance gets fenced off and can
     never commit.
   - Per batch of up to `BATCH_SIZE` consumed records:
     1. `producer.begin_transaction()`.
     2. Transform each event and `producer.produce(OUTPUT_TOPIC, ...)`
        it -- keep this simple (see Transform below), the grading is on
        which `seq`s made it through, not on the transform's business
        logic.
     3. `producer.send_offsets_to_transaction(consumer.position(consumer.assignment()), consumer.consumer_group_metadata())`
        -- this is what ties the CONSUMER's input offsets into the SAME
        transaction as the OUTPUT records. It replaces `consumer.commit()`
        entirely; you never call `consumer.commit()` in this task.
     4. Call `_maybe_crash(processed_count)` somewhere inside this
        open transaction (after step 2, before step 4's commit) so the
        validator's injected crash aborts a real in-flight transaction.
     5. `producer.commit_transaction()`. On any exception in this batch,
        `producer.abort_transaction()` and let the process die or retry
        as appropriate -- don't swallow the error and commit anyway.
   - Why not one transaction per message? At 200k events, a Kafka
     transaction is a multi-round-trip protocol operation (begin, produce
     acks, `send_offsets_to_transaction`, a two-phase commit-marker
     write). Paying that cost once per message instead of once per 5000
     is the difference between finishing in seconds and taking long
     enough to make the exercise painful. Batch it.
2. CLI/behavior contract the validator drives against:
   - Run with `uv run python src/processor.py` from this task's
     directory.
   - Fixed consumer group `t08-processor`, fixed
     `transactional.id="s07-t08-eos"`.
   - Reads `s07.t08.price-updates`, writes `s07.t08.enriched`.
   - Honors `S07_CRASH_AFTER` exactly as `_maybe_crash` already
     implements.
   - Exits `0` once caught up (idle for `IDLE_EXIT_SECONDS`); a run
     killed by the crash hook exits nonzero, expected and fine.
   - Safe to run repeatedly, including resuming after the crash hook
     fired mid-transaction -- the next run must neither reprocess
     already-committed input nor leave the aborted batch's output
     visible to a `read_committed` reader.

## Transform

Keep it deliberately boring -- the point of this task is the transaction
boundary, not the transform. Emit one JSON record per input event to
`s07.t08.enriched`, keyed by `product_id` (same key as the input), carrying
at least: `seq`, `product_id`, `category`, `price`, and one derived field,
e.g. `price_cents = round(price * 100)`. The validator's grading is on the
*set of `seq` values* that show up exactly once downstream -- it does not
care about your derived field's exact business meaning, only that it's
present and consistent.

Try it by hand before trusting the validator:

```bash
uv run python src/processor.py                        # normal run, no crash
S07_CRASH_AFTER=70000 uv run python src/processor.py   # dies mid-transaction
uv run python src/processor.py                         # resumes, catches up
uv run python src/processor.py                         # idle immediately
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Resets `s07.t08.*` topics, creates `s07.t08.price-updates` and
  `s07.t08.enriched` (6 partitions each), and produces the **full** corpus
  (200,000 events) onto the input topic.
- Runs your processor with `S07_CRASH_AFTER=70000` -- expects a nonzero
  exit (the crash hook firing mid-transaction), tolerated.
- Runs your processor again with no crash env, until it exits 0 (caught
  up), generous timeout (~300s).
- Drains `s07.t08.enriched` with an explicit `isolation.level=read_committed`
  consumer, from the beginning of every partition, until idle -- this is
  the read that PROVES exactly-once: a `read_committed` reader never
  surfaces records from an aborted transaction, no matter how many were
  physically written to the log before the crash.
- Asserts: total records read equals `total_events`, and the set of `seq`
  values read equals exactly `{0, ..., total_events - 1}` -- no gaps
  (nothing lost across the crash) and no repeats (nothing double-produced
  across the crash). Also spot-checks a handful of records' derived field.
- A duplicate `seq` is called out explicitly as aborted-transaction
  records leaking through or being committed twice -- check
  `send_offsets_to_transaction` and that you're really reading with
  `read_committed`, not the default `read_uncommitted`.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, the processor script is missing, the crash run exits 0,
any run times out, the output count doesn't match, or the `seq` set has
gaps or duplicates.

## Estimated evenings

1-2

## Topics to read up on

- Kafka transactions: `init_transactions`, `begin_transaction`,
  `send_offsets_to_transaction`, `commit_transaction`, `abort_transaction`
- `transactional.id` and producer-epoch zombie fencing across restarts
- `isolation.level=read_committed` vs `read_uncommitted` on the consumer
  side, and what "the record is in the log but not visible" means
  concretely (control/marker records)
- Why per-message transactions are a throughput disaster and batching the
  commit interval is the standard tradeoff
- The contrast with task 04: Kafka providing the transaction itself
  (this task) vs an external system (Postgres) providing it (task 04) --
  same exactly-once goal, different place the atomicity boundary lives
