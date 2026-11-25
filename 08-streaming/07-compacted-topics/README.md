# 07 — Compacted Topics

## Backstory

Every topic you've used so far in this module retains data by TIME or SIZE:
keep the last N hours, or the last N gigabytes, then delete the oldest
segment. That's the right model for an event log you replay from a point in
history. It is the wrong model for a completely different, very common need:
"what's the current price of product 4213, right now, regardless of how many
times it's been scraped." You don't want the history of every price update
for 5000 products forever — you want one row per product, always up to date,
cheap to hold. RabbitMQ has nothing that does this: a queue is either
consumed (gone) or not yet consumed (still there); there's no notion of "keep
only the latest message per key, forever, and throw the rest away."

Kafka's answer is `cleanup.policy=compact`. A compacted topic is retained not
by age but by KEY: the broker periodically rewrites each log segment, keeping
only the most recently written record for every distinct message key and
discarding every older record with that same key. The topic becomes, in
effect, a changelog for a key-value table — which is exactly the abstraction
Kafka Streams' state stores and ksqlDB's tables are built on. A key can be
removed entirely with a TOMBSTONE: a record with that key and a null value,
which compaction eventually cleans up too (not instantly — see
`delete.retention.ms` if you're curious how long a tombstone itself survives
before the cleaner drops it).

Physical compaction is asynchronous, lazy, and none of it is your problem
today. The log cleaner runs on its own schedule against its own dirty-ratio
threshold; you cannot force it to have run before you read the topic. What
IS your problem: your consumer has to read every record that was EVER
written — compacted or not, because a consumer starting from offset 0 sees
whatever the broker still happens to be holding, which for a mostly-untouched
topic is close to everything — and derive the correct "latest value per key"
itself, the same way the compaction algorithm would. That's `consumer.py`'s
whole job: consume from the beginning, and for each product_id keep only the
value from its highest-seq (most recently published) record.

**Highest-seq, not highest-event_ts — read this twice.** The corpus has late
events: about 2% of records were generated with an `event_ts` that was
pulled backward in time after the fact, while their POSITION in the stream
(their `seq`, and therefore their Kafka offset) stayed exactly where it was
published. Task 05 (windowed aggregation) cared about `event_ts`, because a
window answers "what happened during this 15-minute slice of the world,"
and a late-arriving fact about an earlier moment still belongs to that
earlier moment's window. This task asks a different question — "what's the
last thing anyone told us about this product's price" — and the answer to
that is whatever was PUBLISHED last, i.e. the record with the highest `seq`,
full stop, even if that record happens to carry an earlier `event_ts` than
the row already sitting in your table. This is exactly what real log
compaction does too: it keeps the record with the highest offset for a key,
never mind what timestamp is inside the payload. If you dedup by `event_ts`
instead of `seq`, you will get a handful of products silently wrong — the
late ones — and the validator's sample check is built to catch precisely
that mistake.

## What's given

- `src/setup_topic.py` — a scaffold for creating `s07.t07.latest-price` as a
  compacted topic yourself, so you can watch it in Redpanda Console
  (`localhost:8307`). This is your exploration tool only; the validator
  creates its own independent copy of the topic with the same shape, so
  nothing you do here affects grading.
- `src/consumer.py` — a scaffold: table DDL and connection setup are given,
  the poll loop and the upsert are `raise NotImplementedError`.
- The stack: redpanda at `localhost:19092`, warehouse Postgres at
  `localhost:54307` (db `streaming`), Redpanda Console at `localhost:8307`.
- `harness/common.py` — `kafka_bootstrap()`, `pg_connect()`, `create_topic()`
  (accepts `cleanup_policy` and `extra_config`), etc.

## What's required

1. Implement `src/setup_topic.py`: create `s07.t07.latest-price` with
   `cleanup_policy="compact"` and compaction knobs aggressive enough to
   actually observe compaction during a short session (the TODO comment
   names the two knobs and what they control). Run it, produce some events
   at the topic (you can reuse `harness.common.produce_events` from a
   throwaway script, or just point at the full corpus), and watch Redpanda
   Console's topic view — segment count should drop as the cleaner runs.
   This step is for your own understanding; nothing here is graded directly.
2. Implement `src/consumer.py`:
   - The poll loop: same shape as task 02/03/04's consumers —
     `consumer.poll()`, track idle time, decode JSON, exit 0 once idle
     `IDLE_EXIT_SECONDS`.
   - `upsert_latest(conn, event)`: `INSERT ... ON CONFLICT (product_id) DO
     UPDATE ... WHERE EXCLUDED.seq > core.t07_latest_price.seq`. That WHERE
     clause is the whole point of the task — without it, an out-of-order
     redelivery, a rerun, or (in a differently-partitioned setup) records
     arriving to different consumer group members in a different relative
     order could overwrite a newer row with an older one. `DO NOTHING` for
     the case where the incoming seq is not newer is what the WHERE clause
     buys you — check what `ON CONFLICT ... DO UPDATE ... WHERE <cond>`
     does when `<cond>` is false: it's not an error, it's a silent no-op for
     that row, which is exactly what you want.
   - Remember the psycopg gotcha from earlier tasks: don't rely on
     `with conn:` to manage the connection here — use `conn.cursor()` plus
     an explicit `conn.commit()`.
3. CLI/behavior contract the validator drives against:
   - `uv run python src/consumer.py` from this task's directory.
   - Fixed consumer group id `t07-consumer`.
   - Consumes `s07.t07.latest-price` from the beginning.
   - Materializes `core.t07_latest_price(product_id INT PRIMARY KEY, price
     NUMERIC NOT NULL, currency TEXT NOT NULL, in_stock BOOLEAN NOT NULL,
     event_ts TIMESTAMPTZ NOT NULL, seq BIGINT NOT NULL)`.
   - Exits 0 once idle `IDLE_EXIT_SECONDS` (caught up). Safe to rerun.

Try it by hand before trusting the validator:

```bash
uv run python src/setup_topic.py
uv run python src/consumer.py
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Resets `s07.t07.*` topics and re-creates `s07.t07.latest-price` itself as a
  compacted topic (6 partitions) — independent of your `setup_topic.py`, so
  grading is deterministic. Asserts (via `describe_configs`) that the topic's
  `cleanup.policy` actually contains `compact`.
- Produces the FULL 200,000-event corpus into the topic, keyed by
  `product_id`.
- Drops `core.t07_latest_price` so your consumer recreates it, then runs
  `uv run python src/consumer.py`, timeout ~300s, must exit 0.
- Asserts against `data/ground-truth.json`'s `latest_state`:
  - `count(*)` in `core.t07_latest_price` equals `latest_state.count`.
  - `sum(price)` matches `latest_state.price_sum` within `0.05`.
  - Each of the 20 `latest_state.sample` product_ids is present with
    `price` (within `0.005`), `currency`, `in_stock`, and `seq` matching
    exactly. A consumer that deduped by `event_ts` instead of `seq` will
    fail this check by name for whichever sample products happened to have
    a late event as their true last write — read the failure message, it
    names the product and the seq mismatch.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the stack
is down, `core.t07_latest_price` is missing or empty after the run, the
consumer times out or exits nonzero, or any of the count/sum/sample checks
fail.

## Estimated evenings

1

## Topics to read up on

- `cleanup.policy=compact` vs `cleanup.policy=delete`: retention by key vs
  retention by time/size, and why they're not mutually exclusive
  (`compact,delete` is a valid combined policy, not used here)
- The log cleaner: `min.cleanable.dirty.ratio`, `segment.ms`, and why
  compaction is asynchronous and best-effort rather than synchronous with
  the write
- Tombstones: a record with a null value as a "delete this key" marker, and
  `delete.retention.ms` controlling how long a tombstone itself survives
  before the cleaner removes it too
- Why compaction operates on the Kafka message KEY, never on any field
  inside the value — and why that means your key choice (`product_id` here)
  IS your compaction granularity
- `INSERT ... ON CONFLICT ... DO UPDATE ... WHERE <condition>`: a
  conditional upsert, and why it's different from an unconditional
  `DO UPDATE`
- Why "last write wins" needs a total order to mean anything, and why
  Kafka offset (equivalently, this corpus's `seq`) is that order while
  `event_ts` is not — contrast directly with task 05
