# 08 -- Capstone: Scrape-Ingestion Control-Plane

## Backstory

Your scraper team has spent this module building the pieces: a per-domain rate
limiter (task 01), a distributed lock (02), a dedup filter (03), a Redis
Streams consumer (04), and a MongoDB document model (05). Now the business
wants the thing those pieces were for. Many worker processes are scraping the
catalog around the clock and firing a raw event every time they observe a
product -- `{event_id, product_id, price, scraped_at, ...}`. Prices drift: the
same product gets re-observed at different times for different amounts. What
the dashboards need is not the raw firehose but the **current state**: for
every product ever scraped, its LATEST observed price, so the team can answer
"how many distinct products are we tracking", "what's the total value of the
catalog right now", and "how does that break down per category".

So you have to materialize a current-state view out of the event stream and
keep it correct. The catch is that delivery is only ever **at-least-once**. A
consumer can read a batch of events and then crash before it finishes writing
them -- those events sit in the group's pending list, owned by a worker that
never comes back, and someone else has to pick them up and reprocess them.
Reprocessing means the same event can hit your materialization two or three
times, possibly out of order relative to other events for the same product
(the stream is not in chronological order). If your write logic is naive --
"upsert whichever arrives last" or "skip if we've already seen this product"
-- a redelivery or a reclaim will quietly clobber a fresh price with a stale
one, or freeze a product on its first-seen value forever. The capstone is
proving that **at-least-once delivery plus an idempotent, watermarked
materialize equals effectively-once STATE**: the view converges to exactly the
right numbers even across a crash.

## What's given

- `src/pipeline.py` -- six stubs, each `raise NotImplementedError`, with rich
  docstrings spelling out the exact contract: `produce`, `ensure_group`,
  `materialize`, `run_consumer`, `reclaim_and_run`, `current_state_summary`.
- `DESIGN.md` -- a design-memo template with five sections to fill in for CP3.
- The live stack: Redis on `localhost:6310`, MongoDB on `localhost:27310`
  (database `sandbox`). See `harness/common.py` for `redis_client()` /
  `mongo_db()` / `redis_flush_prefix`.
- `data/events.json` -- the raw scrape event stream (NDJSON). The validators
  join each event's real catalog `category` in from `data/products.json`
  before pushing it, so `produce()` receives events that already carry
  `category`.
- `data/ground-truth.json` -- the committed answer key. The key this task
  cares about is `current_state` (`count`, `price_sum`, `per_category_count`).
- Three checkpoint validators: `tests/validate_cp1.py`, `validate_cp2.py`,
  `validate_cp3.py`, plus `tests/validate.py` which runs all three in order as
  a convenience.

## What's required

Implement all six functions in `src/pipeline.py`. Every Redis key you touch
must live under `s10:t08:` and every Mongo collection under `t08_` -- the three
services are shared across this module's tasks. The work is graded in three
checkpoints.

### CP1 -- steady convergence (`validate_cp1.py`)

**Build:** the base pipeline. `produce()` pushes the full event stream onto a
Redis Stream; `ensure_group()` idempotently creates the consumer group;
`run_consumer()` reads with `XREADGROUP`, calls `materialize()`, and `XACK`s
each batch; `materialize()` upserts into `t08_state` keyed by `product_id`,
keeping only the observation with the newest `(scraped_at, event_id)`
watermark; `current_state_summary()` reads the view back as
`{count, price_sum, per_category_count}`.

**Checked:** the validator drains the whole stream with **two** consumers in
the same group (so a single-reader shortcut can't hide a group bug), asserts
every entry was processed and nothing is left pending (`XPENDING` == 0), then
compares `current_state_summary()` against ground truth's `current_state` --
`count` exact, `price_sum` within a small tolerance, `per_category_count`
exact per category. This is the no-crash base case.

### CP2 -- chaos: crash + reclaim convergence (`validate_cp2.py`)

**Build:** `reclaim_and_run()`, which uses `XAUTOCLAIM` with a `min_idle_ms`
threshold to steal entries left pending by a dead consumer, then materializes
and acks them just like the normal loop. Your `materialize()` must be genuinely
idempotent and watermark-ordered, so replaying reclaimed entries -- possibly a
second or third time, possibly out of order -- can only ever advance the state
to what it should be, never regress or double-count it.

**Checked:** the validator splits the stream into three ranges. One consumer
processes the first 50% normally; the next 20% is read into that consumer's
pending list and then deliberately abandoned (the simulated crash -- entries
sit in the PEL, unacked, owned by a consumer that never returns); the final
30% is untouched backlog. A fresh consumer then `reclaim_and_run()`s the
abandoned batch and drains the rest. The final `current_state_summary()` must
STILL match ground truth exactly and `XPENDING` must be 0. The validator first
proves, from the corpus itself, that hundreds of products genuinely need an
overwrite across the crash boundary -- so a non-watermarked implementation
cannot pass by luck.

### CP3 -- design memo + green re-run (`validate_cp3.py`)

**Build:** fill in all five sections of `DESIGN.md` with your own analysis --
the control-plane architecture and why each Redis primitive; the idempotency /
watermark argument; the crash-recovery flow; where per-domain rate shaping
would sit in a real deployment; and the broader failure modes.

**Checked:** every required section is present and filled with real content
(no leftover placeholder), THEN CP1 and CP2 are re-run as subprocesses and both
must still pass -- a memo for a pipeline that no longer converges does not pass.

## Completion criteria

Run, from this task's directory, either each checkpoint in turn or the full
sequence:

```bash
uv run python tests/validate_cp1.py
uv run python tests/validate_cp2.py
uv run python tests/validate_cp3.py
# or, all three at once:
uv run python tests/validate.py
```

The task is complete when all three checkpoint validators print `PASSED` and
exit 0 (equivalently, `validate.py` reports all three green). Any failure --
including a stub still raising `NotImplementedError`, an unfilled `DESIGN.md`,
or the stack being unreachable -- prints a single `NOT PASSED: <reason>` line
and exits 1.

## Estimated evenings

3-4

## Topics to read up on

- Idempotent upserts: writing the same record more than once must leave the
  same result, and why that is the property that makes at-least-once delivery
  safe
- Materialized current-state / latest-per-key views: collapsing an event
  stream down to one row per key by a "latest wins" rule
- Watermark / version comparison for "latest": using a strict total order
  (here `(scraped_at, event_id)`) so replays and out-of-order arrivals resolve
  deterministically, instead of "whichever wrote last" or "first seen wins"
- Crash recovery and at-least-once processing with Redis Streams consumer
  groups: the Pending Entries List, `XACK`, `XPENDING`, and reclaiming
  abandoned work with `XAUTOCLAIM` and a `min_idle_ms` idle threshold
- MongoDB `bulk_write` / `UpdateOne` with `upsert=True`: applying a batch of
  keyed writes efficiently, and how to make the write conditional on the
  incoming record being newer

## Off-limits

`.authoring/` (at the module root) holds the full data contract, RNG draw
order, and the shared namespacing convention for every task in this module --
spoilers. Don't read it before finishing this task.
