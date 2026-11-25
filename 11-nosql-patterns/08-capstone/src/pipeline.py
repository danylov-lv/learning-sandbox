"""s10.t08 capstone -- the scrape-ingestion control-plane.

Story: raw scrape events arrive from many workers. A per-domain rate limiter
(task 01's mechanism) is supposed to shape intake before anything reaches
here -- that's a real production concern, discussed in DESIGN.md, but this
module's checkpoints grade convergence over the FULL accepted event stream,
so `produce()` itself does no admission control. Accepted events land on a
Redis Stream; a consumer group (task 04's mechanism) reads them and
materializes a current-state product view into MongoDB, IDEMPOTENTLY --
upserting by product_id, keeping only the LATEST observation by
`(scraped_at, event_id)`. At-least-once delivery (a message can be read more
than once: redelivered after a crash, reclaimed from a dead consumer's
pending list) plus an idempotent, watermarked materialization equals
effectively-once STATE, even though the underlying delivery was never
exactly-once.

You implement six functions:

  * `produce(client, stream_key, events)` -- push accepted events onto the
    stream.
  * `ensure_group(client, stream_key, group)` -- idempotently create the
    consumer group.
  * `materialize(db, entries)` -- the heart of the checkpoint: apply a batch
    of stream entries to `t08_state`, keyed by product_id, keeping only the
    winner by `(scraped_at, event_id)`.
  * `run_consumer(client, db, stream_key, group, consumer, *, max_messages=None)`
    -- the normal read/materialize/ack loop.
  * `reclaim_and_run(client, db, stream_key, group, consumer, min_idle_ms)`
    -- steal and finish another (dead) consumer's abandoned pending entries.
  * `current_state_summary(db)` -- read `t08_state` back out in the shape
    graded against `data/ground-truth.json`'s `current_state`.

Every Redis key you touch must live under `s10:t08:` and every Mongo
collection under `t08_` -- the three services are shared across this
module's 8 tasks (see `.authoring/design.md`, off-limits until you're done).

Try each piece by hand before trusting the validators:

    uv run python tests/validate_cp1.py
    uv run python tests/validate_cp2.py
"""

STATE_COLLECTION = "t08_state"


def produce(client, stream_key, events) -> None:
    """Push every event in `events` onto the Redis Stream at `stream_key` via
    `XADD`, one stream entry per event.

    `client` is a live `redis.Redis` (see `harness.common.redis_client`, called
    with `decode_responses=True` by the validators -- so field values you read
    back later will already be `str`, not `bytes`). `events` is an iterable of
    plain dicts, each with at least: `event_id` (int), `product_id` (int),
    `price` (float), `category` (str -- the event's real catalog category,
    already joined in by the caller; the raw scrape event itself doesn't carry
    category, see `.authoring/design.md`), and `scraped_at` (str, ISO-8601,
    e.g. `"2025-04-17T13:05:22"`).

    For each event, `XADD stream_key '*' event_id=... product_id=...
    price=... category=... scraped_at=...` (a Python dict passed as the
    `fields` argument to `client.xadd(...)` is the natural shape; redis-py
    stringifies numeric values for you, but `materialize()` will need to
    parse them back out of the stream, since Redis Streams store everything
    as strings).

    Use `'*'` as the entry ID (let Redis assign one) -- nothing downstream
    depends on entry IDs being meaningful, only on being able to XACK
    whatever ID XREADGROUP handed back.

    Does not read anything back and does not gate/drop events -- that's a
    rate limiter's job (task 01), not this function's. If a caller wants
    admission control, it filters `events` before calling `produce`.
    """
    raise NotImplementedError


def ensure_group(client, stream_key, group) -> None:
    """Idempotently create a consumer group named `group` on `stream_key`.

    Use `XGROUP CREATE stream_key group <id> MKSTREAM`. `MKSTREAM` means the
    stream itself gets created (empty) if it doesn't exist yet, so this is
    safe to call before any `produce()` call. Pick `<id>` as `'0'` (the very
    start of the stream), NOT `'$'` (only future entries) -- `'0'` means
    every entry ever written to the stream, including ones written before
    this group existed, is still eligible for delivery via `XREADGROUP ...
    '>'`. That matters here because it makes this function's behavior
    independent of whether you call it before or after `produce()`.

    Calling `XGROUP CREATE` on a group that already exists raises a
    Redis error whose message contains `BUSYGROUP` -- catch exactly that
    case and treat it as success (this function must be safe to call
    repeatedly, e.g. once per consumer that starts up). Any OTHER error
    should propagate.
    """
    raise NotImplementedError


def materialize(db, entries) -> int:
    """Apply a batch of stream entries to `t08_state`, IDEMPOTENTLY.

    `db` is a live Mongo database (`harness.common.mongo_db()`). `entries` is
    an iterable of `(entry_id, fields)` pairs -- exactly the shape
    `XREADGROUP`/`XAUTOCLAIM` hand back: `entry_id` is the stream entry ID
    (a string, opaque to you here), `fields` is a dict of the string-valued
    fields you wrote in `produce()` (so parse `product_id`/`event_id` back
    to `int`, `price` back to `float`; `category` and `scraped_at` are
    already the right type as plain strings).

    For each entry, upsert into the `t08_state` collection keyed by
    `product_id`, but ONLY if this entry's `(scraped_at, event_id)` is
    STRICTLY newer than whatever is already stored for that product_id (or
    nothing is stored yet). An older-or-equal entry -- a duplicate
    redelivery of a message already applied, or a stale reclaim racing a
    fresher normal read -- must be a complete no-op: don't touch the
    document, don't change what it reports for that product.

    Why `(scraped_at, event_id)` and not just `scraped_at`: two events can
    share a `scraped_at` second in this corpus; `event_id` (unique, 1..N)
    breaks the tie deterministically, so "latest" is a strict total order
    with no ambiguity.

    Why this can't be "skip if product_id already has a document": stream
    delivery order is NOT chronological order (events are shuffled when the
    stream is built -- see `.authoring/design.md` -- so a lower-`event_id`,
    later-`scraped_at` observation can arrive AFTER a higher-`event_id`,
    earlier-`scraped_at` one already got materialized). An
    existence-check-only "dedup" would silently keep a stale price forever
    once any observation for a product has landed. The comparison must be
    on the WATERMARK `(scraped_at, event_id)`, every single time, not on
    whether a document merely exists.

    Store at least: `product_id`, `price`, `category`, `scraped_at`,
    `event_id` per document (enough for `current_state_summary` to answer
    `count` / `price_sum` / `per_category_count` straight out of this
    collection with no other lookups).

    This must be safe to call with the SAME entries more than once (a
    redelivered/reclaimed message looks identical to its first delivery) and
    safe to call with entries in ANY relative order across separate calls
    (batch B applied before batch A, or vice versa, must reach the same
    final state) -- that's the whole idempotency argument this checkpoint
    is testing.

    Returns the number of entries in this batch that actually changed
    stored state (a fresh insert or a genuine watermark advance) -- a
    no-op (stale/duplicate) entry does not count. This is a return value
    for your own instrumentation/debugging; the validators grade the
    resulting `t08_state` contents, not this count.
    """
    raise NotImplementedError


def run_consumer(client, db, stream_key, group, consumer, *, max_messages=None) -> int:
    """The steady-state read loop for one named consumer in `group`.

    Repeatedly: `XREADGROUP GROUP group consumer COUNT n STREAMS stream_key
    '>'` to claim a batch of not-yet-delivered entries, `materialize(db,
    batch)` to apply them, then `XACK stream_key group <entry ids...>` to
    mark them done. `'>'` means "only entries never delivered to ANY
    consumer in this group before" -- this is the normal forward-progress
    read, distinct from `reclaim_and_run`'s job of picking up entries
    ALREADY delivered (to some other, now-dead, consumer) but never acked.

    Stop and return the total number of entries processed once either (a)
    `max_messages` have been processed, if `max_messages` is not `None`, or
    (b) `XREADGROUP` reports no more new entries available (empty read --
    the stream's backlog for this group is exhausted). Do not block forever
    waiting for entries that will never arrive; a validator may call this
    with `max_messages` set to a fraction of the stream on purpose, to stop
    a "consumer" partway through and simulate a crash -- the entries it
    already read into its own pending list before stopping are exactly what
    `reclaim_and_run` needs to be able to pick up later.

    `max_messages=None` (the default) means "drain until the stream has
    nothing left to offer this group" -- the steady-state (no crash) case.

    Returns the number of entries actually processed (acked), which may be
    less than `max_messages` if the stream ran out first.
    """
    raise NotImplementedError


def reclaim_and_run(client, db, stream_key, group, consumer, min_idle_ms) -> int:
    """Steal and finish another (dead) consumer's abandoned pending entries.

    A consumer that read entries via `XREADGROUP` but crashed before calling
    `XACK` leaves those entries in the group's Pending Entries List (PEL),
    permanently attributed to a consumer name that will never come back to
    finish them (see `XPENDING`). `XAUTOCLAIM stream_key group consumer
    min_idle_ms start_id COUNT n` reassigns any such entries -- ones idle for
    at least `min_idle_ms` milliseconds since their last delivery, regardless
    of which (possibly dead) consumer they were assigned to -- to `consumer`,
    and hands them back to you to finish, exactly like a fresh `XREADGROUP`
    read would.

    Loop `XAUTOCLAIM` (starting `start_id='0-0'`, then following the cursor
    it returns each call) until it reports no more entries meeting the
    idle-time threshold. For each non-empty batch it returns:
    `materialize(db, batch)` then `XACK` those entry IDs, same as
    `run_consumer`. Stop when a call returns no claimed entries AND the
    returned cursor is `'0-0'` (a full pass over the PEL with nothing left
    to claim).

    Because `materialize` is watermarked and idempotent, it does not matter
    whether the entries this reclaims were partially applied already, fully
    applied already, or never applied at all before the crash -- reapplying
    them here can only ever advance `t08_state` to what it should have been,
    never regress it or double-count it.

    Returns the total number of entries reclaimed and processed this call.
    """
    raise NotImplementedError


def current_state_summary(db) -> dict:
    """Read `t08_state` back out as the graded current-state summary.

    Returns `{"count": int, "price_sum": float, "per_category_count": {cat:
    int, ...}}`:

      * `count` -- the number of documents in `t08_state` (one per distinct
        product_id ever materialized).
      * `price_sum` -- the sum of the (latest, materialized) `price` across
        every document, rounded to 2 decimals.
      * `per_category_count` -- `{category: count}`, the number of
        documents whose stored `category` is that category (only categories
        actually present need to appear).

    This is graded against `data/ground-truth.json`'s `current_state`:
    `count` exact, `price_sum` within a small float tolerance,
    `per_category_count` exact per category.
    """
    raise NotImplementedError
