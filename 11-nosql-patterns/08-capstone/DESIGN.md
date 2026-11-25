# Capstone Design Memo -- Scrape-Ingestion Control-Plane

Fill in each section with your own analysis, grounded in what you built and
observed across CP1 and CP2 of this capstone, and across tasks 01-04 of this
module (the rate limiter, the distributed lock, dedup, and Redis Streams).

## Control-plane architecture

(fill in -- walk through the stages raw scrape events pass through in this
capstone's story: a per-domain rate limiter, a Redis Stream, a consumer
group, MongoDB materialization. For each Redis primitive you actually used
-- the Stream, the consumer group, XACK, XAUTOCLAIM -- say specifically why
that primitive and not a simpler one, e.g. why a Stream instead of a plain
List or Pub/Sub for this workload, why a consumer GROUP instead of a single
reader)

## Idempotency and the watermark argument

(fill in -- state the effective-once argument precisely: at-least-once
delivery plus an idempotent materialize equals effectively-once STATE. What
exactly does `materialize()` compare to decide "newer" versus "no-op", and
why is `(scraped_at, event_id)` the right total order rather than just
`scraped_at` or just delivery order. Why would a naive "upsert whichever
arrives last" or "skip if the product already has a document" strategy have
broken CP1 or CP2, concretely -- cite what you observed)

## Crash recovery flow

(fill in -- trace what actually happens end to end when a consumer crashes
mid-batch: what state is left in the group's Pending Entries List, what
`XPENDING` shows, how `XAUTOCLAIM` with a `min_idle_ms` threshold picks those
entries back up, and why re-materializing them -- possibly a second or third
time, possibly out of their original relative order -- cannot corrupt
`t08_state` given the watermark argument above. Reference the actual CP2
numbers: how many entries were reclaimed, how many products needed a genuine
overwrite across the crash boundary)

## Per-domain rate shaping

(fill in -- CP1/CP2 push the FULL accepted event stream with no admission
control, because the grading target is full convergence to ground truth. In
a real deployment, where would a per-domain rate limiter (task 01's atomic
check-and-record) sit relative to `produce()`, what would it actually gate,
and what's the tradeoff between DROPPING an over-limit scrape versus
queueing/delaying it -- and how does that choice interact with the
idempotent materialization downstream)

## Failure modes

(fill in -- beyond the single-crash scenario CP2 tests, what else can go
wrong in this control-plane and how would you detect or guard against each:
a "poison" message that always fails to materialize, a consumer that claims
work via XAUTOCLAIM but is ALSO about to die (a reclaim race), clock skew or
a bad `scraped_at` value corrupting the watermark ordering, the group's PEL
growing unbounded if nothing ever reclaims, MongoDB write failures mid-batch)
