# 05 — Windowed Aggregation

## Backstory

Every consumer you've built in this module so far has processed events in
whatever order the log handed them to you. That's fine when the question is
"what's the latest price for product X" or "did every event get written
exactly once" — order of arrival and order of the thing itself line up.

But a lot of real analytics questions aren't about arrival order at all.
"How many electronics price-updates happened between 00:15 and 00:30 on
2025-07-01" is a question about EVENT TIME — the moment the thing you're
measuring actually happened — not about when your consumer happened to read
it off the wire. Those two clocks agree most of the time, which is exactly
what makes it easy to write a windower that silently uses the wrong one and
still passes a casual smoke test.

This task's corpus won't let that slide. About 2% of events are "late": the
scraper's timestamp says the price was observed several minutes before it
actually got published to the topic. Real systems produce late events
constantly — a mobile client buffering while offline, a batch job that
enriches and re-emits, a straggling partition replica, clock skew between
producers. A consumer that windows by Kafka offset (or by wall-clock time of
processing) puts every one of those late events in the wrong 15-minute
bucket. A consumer that windows by the event's own `event_ts` puts it where
it actually belongs, no matter how late it showed up in the log.

## What's given

- `src/consumer.py` — a scaffold consuming `s07.t05.price-updates` (group
  `t05-consumer`) from the beginning. It ships:
  - the DDL for `mart.t05_window_category` and an `ensure_table()` helper,
  - `WINDOW_START` / `WINDOW_SIZE` constants (15-minute tumbling windows
    anchored at `2025-07-01T00:00:00Z`),
  - TODOs for `window_start_for(event_ts)` (parse + floor to the window
    start) and `upsert(conn, window_start, category, price)` (increment
    `cnt` / `price_sum` for that key),
  - TODO for the `Consumer` construction, `subscribe()`, and a poll loop
    that runs until the topic has been idle ~10s, then commits and exits 0.
- The stack: redpanda at `localhost:19092`, warehouse Postgres at
  `localhost:54307` (db `streaming`).
- `harness/common.py` — `kafka_bootstrap()`, `pg_connect()`, etc.

## What's required

1. Implement `window_start_for(event_ts)`: parse the ISO 8601 UTC timestamp
   and floor it to the start of its 15-minute tumbling window, anchored at
   `WINDOW_START = 2025-07-01T00:00:00Z`. This is the whole task — get the
   flooring right and windowing by event time (as opposed to offset or
   processing time) falls out automatically, because you never look at
   where the message sat in the log.

2. Implement `upsert(conn, window_start, category, price)`: one row per
   `(window_start, category)` in `mart.t05_window_category`, incrementing
   `cnt` by 1 and `price_sum` by `price` — a single `INSERT ... ON CONFLICT
   ... DO UPDATE`, not a select-then-update.

3. Wire up the `Consumer` (`bootstrap.servers`, `group.id=t05-consumer`,
   `auto.offset.reset="earliest"`), `subscribe()` to
   `s07.t05.price-updates`, and write the poll loop: for each message,
   decode JSON, compute the window start from `event_ts`, upsert
   `(window_start, category)` with the event's `price`. There is no
   natural end-of-stream signal in Kafka — track time since the last real
   message and exit once it exceeds the idle timeout, committing whatever's
   pending first.

4. Run it by hand from this task's directory (create the topic and produce
   some events first if you're testing manually — the validator does both
   for you):

   ```bash
   uv run python src/consumer.py
   ```

   Then spot-check a window in Postgres:

   ```sql
   SELECT * FROM mart.t05_window_category ORDER BY window_start, category;
   ```

## Event time vs processing time vs ingestion time

Three different clocks show up in any streaming system, and it's worth
being precise about which one you're using:

- **Event time**: when the thing being described actually happened —
  here, `event_ts`, the moment the scraper observed the price. This is a
  property of the event's payload, not of the pipeline.
- **Ingestion time**: when the event was appended to the Kafka log (its
  offset's implicit timestamp). Monotonic within a partition, by
  construction — that's the whole reason offsets are useful for
  replay/exactly-once — but it says nothing about when the event's subject
  actually occurred.
- **Processing time**: when YOUR consumer happens to read and handle the
  event. Depends on consumer lag, restarts, rebalances — the least
  meaningful clock of the three for answering a question like "how much
  activity happened in this 15-minute period," yet the easiest one to
  accidentally use, because it's just "whatever `datetime.now()` returns
  when your loop gets to this message."

`window_category_agg` in the ground truth is built strictly from event
time. Windowing by ingestion/offset order or by processing time will
disagree with it — not randomly, but specifically on the ~2% of events this
corpus deliberately relocates.

## Tumbling windows and flooring

A tumbling window partitions time into fixed-size, non-overlapping, back-
to-back intervals: `[00:00, 00:15)`, `[00:15, 00:30)`, ... Every event
belongs to exactly one window, determined entirely by its timestamp — no
event can straddle two windows or belong to zero.

Assigning an event to its window is a flooring operation: given a window
size `W` and an anchor `T0`, the window start for timestamp `t` is `T0 +
floor((t - T0) / W) * W`. It's the same integer-division-into-buckets idea
you'd use to compute which page a byte offset falls on — just applied to a
duration instead of a count. Get the anchor and the floor direction right
and every timestamp in `[00:00:00Z, 02:00:00Z)` lands in exactly one of the
8 windows this corpus defines.

## Why the late 2% breaks offset/processing-time windowing

The corpus is built with EVENTS in non-decreasing event-time order, then
Kafka `seq` / offset assigned to match that order — so far, offset and
event time agree. Afterward, ~2% of events are selected and their
`event_ts` is pulled 1-15 minutes earlier (clamped so it never falls
before the corpus start), WITHOUT moving their position in the file. The
result: offset (and therefore ingestion time, and therefore whenever your
consumer processes it) still increases monotonically, but `event_ts` no
longer does. A late event sits at a LATER offset than events with a LARGER
`event_ts` — it appears to arrive "in the future" relative to its own
timestamp.

If you window by offset order (e.g. "bucket messages 1-N into window 1,
N+1-2N into window 2") or by processing time (e.g. "bucket by
`datetime.now()` when I read this message"), every late event lands in
whatever window happens to be current when it's read — which is later,
sometimes much later, than the window its `event_ts` actually belongs to.
Only reading `event_ts` out of the payload and flooring THAT gets every
event, late or not, into its correct bucket.

## UTC handling

Every timestamp in this corpus — `event_ts`, the window boundaries, the
ground truth keys — is UTC, formatted with a trailing `Z`. Keep everything
in UTC end to end: parse `event_ts` into a timezone-aware `datetime` (don't
strip the timezone and treat it as naive), store `window_start` as
`timestamptz` in Postgres (which normalizes to UTC internally regardless of
session timezone), and when reading it back, be explicit that you want UTC
rather than trusting a client/session default. A silent local-timezone
conversion anywhere in this chain shifts every window boundary and fails
the validator in a way that's confusing to debug because the counts look
"almost right."

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It resets
the module's topics, creates `s07.t05.price-updates` with 6 partitions,
produces the full 200k-event corpus, drops `mart.t05_window_category` (so
your consumer's DDL has to actually run), launches `src/consumer.py` as a
subprocess, and once it exits, compares `mart.t05_window_category` against
the ground truth's `window_category_agg`:

- the exact same set of `(window_start, category)` keys appear in both,
- every `cnt` matches exactly,
- every `price_sum` matches within 0.05,
- the grand total of `cnt` across every window/category equals the
  ground truth's `total_events` (200000).

Prints `PASSED: <n> window/category cells matched exactly, ...` on success,
`NOT PASSED: <reason>` and exits 1 otherwise — including a precise
`window <w> category <c> got N expected M` when a specific cell disagrees
(the signature of a late event landing in the wrong bucket).

## Estimated evenings

1

## Topics to read up on

- Event time vs processing time vs ingestion time in streaming systems
- Tumbling windows vs sliding/hopping windows vs session windows (this
  task only needs tumbling, but knowing the shape of the others helps you
  recognize when you'd reach for them)
- Watermarks — the general mechanism real stream processors (Flink, Kafka
  Streams) use to decide when a window is "done" in the presence of
  lateness; this task sidesteps watermarks by processing the whole bounded
  corpus and closing every window at the end, but production systems can't
  assume the stream ever ends
- `datetime.fromisoformat` and UTC-aware vs naive datetimes in Python
- Postgres `timestamptz` semantics — why it's safe to store/compare across
  session timezones
- `INSERT ... ON CONFLICT ... DO UPDATE` for streaming aggregation
  (upsert-as-accumulator, same idea as task 04's exactly-once upsert,
  applied per window/category instead of per key)
