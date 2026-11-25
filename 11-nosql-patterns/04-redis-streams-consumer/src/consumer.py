"""s10.t04 -- Redis Streams as an at-least-once work queue with consumer groups.

A Redis Stream (`XADD`/`XREAD`) is an append-only log, much like a Kafka
partition -- entries get monotonic IDs and stick around after being read.
What Kafka calls a *partition*, Streams calls a *stream*; what Kafka calls a
*consumer group with committed offsets*, Streams calls a *consumer group with
a Pending Entries List (PEL)*. The mechanics differ in a way that matters:

- Kafka: a consumer commits an OFFSET ("I'm done up through position N").
  Everything at or before that offset is implicitly done; there's no
  per-message acknowledgement.
- Redis Streams: `XREADGROUP` delivers an entry to a named consumer AND
  records it in the group's PEL (a per-entry, per-consumer "in-flight"
  table). The entry stays in the PEL, tagged as pending for that consumer,
  until something explicitly `XACK`s it. Ack is per-MESSAGE, not per-offset.

That per-message PEL is what makes recovery from a crashed consumer look
different from Kafka. In Kafka, a crashed consumer's partition gets
reassigned to another group member during a rebalance, which resumes reading
from the last committed offset -- coarse-grained, offset-based. In Streams,
any OTHER consumer in the group can inspect the PEL (`XPENDING`), find
entries that have been sitting unacked longer than some `min-idle-time`, and
steal them one by one (`XCLAIM`, or the more convenient `XAUTOCLAIM`) without
touching entries other consumers are still legitimately working on. This
module's task: build the four/five primitives that make that recovery
possible, then prove it works by killing a consumer mid-batch (without
faking a graceful shutdown) and having another consumer finish its work.

Wire format: every stream entry has exactly one field, "payload", whose
value is `json.dumps(event)` for the event dict passed to `produce`. Do not
flatten the event's own fields into separate stream fields -- `payload` is
the single source of truth every function in this module (and the
validator) reads back with `json.loads`.

Every key this module touches MUST live under the `s10:t04:` namespace --
the Redis instance is shared across every task in this module.
"""

import json


def produce(client, stream_key, events):
    """Append each event in `events` onto `stream_key` as a new stream entry.

    For each event (a dict, e.g. one line of `data/events.json` already
    parsed into a Python dict), call `XADD` with a single field:

        {"payload": json.dumps(event)}

    Let Redis assign the entry ID (pass `id="*"` / the redis-py default) --
    do not try to derive an ID from `event["event_id"]` yourself; stream IDs
    and event IDs are different things. Preserve the order of `events`: add
    them in the order given, so the stream's entry order matches the input
    order (later code that reasons about "the same event re-delivered" does
    not depend on order, but a stable, predictable stream is easier to
    reason about while you're building this).

    Args:
        client: a connected `redis.Redis` (decode_responses=True).
        stream_key: the stream's key, always under `s10:t04:` (e.g.
            `s10:t04:stream`). Don't hardcode it here -- the caller decides
            the exact key.
        events: a list of JSON-serializable dicts.

    Returns:
        None. (If you want to sanity-check your own work while developing,
        `client.xlen(stream_key)` tells you how many entries exist.)
    """
    raise NotImplementedError


def ensure_group(client, stream_key, group):
    """Create `group` as a consumer group on `stream_key`, tolerating the
    case where it already exists.

    Use `XGROUP CREATE` with `MKSTREAM` so the group can be created even
    before any entry has been produced (the stream key is created empty as
    a side effect if it doesn't exist yet) -- start the group's read
    position at the beginning (`id="0"`) rather than `"$"` (which would mean
    "only entries added after this point"), since this module always wants
    a fresh group to be able to see everything already produced.

    Calling `XGROUP CREATE` a second time for a group that already exists
    raises a Redis `BUSYGROUP` error. That is not a failure here -- catch it
    and treat it as "the group is already set up, nothing to do". Any OTHER
    error should propagate.

    Args:
        client: a connected `redis.Redis`.
        stream_key: the stream's key.
        group: the consumer group's name (a plain string, not necessarily
            namespaced itself -- it's scoped to `stream_key`).

    Returns:
        None.
    """
    raise NotImplementedError


def consume_new(client, stream_key, group, consumer, count):
    """Read up to `count` NEW (never-before-delivered-to-anyone) entries for
    `consumer` in `group`, via `XREADGROUP ... STREAMS stream_key >`.

    The special ID `">"` means "entries never yet delivered to any consumer
    in this group" -- as opposed to a concrete ID, which would replay
    history already delivered to (specifically) `consumer`. Every entry this
    call returns is, as a side effect of `XREADGROUP`, added to the group's
    Pending Entries List (PEL) under `consumer`'s name -- it is now "in
    flight" and stays there until something `XACK`s it (or another consumer
    reclaims it -- see `reclaim`). This function does NOT ack anything; that
    is the caller's job once it has actually processed the entries. That
    split -- read leaves work pending, a separate explicit step retires it
    -- is exactly what makes crash recovery possible: if the caller dies
    between this call and acking, the entries are still sitting in the PEL,
    reclaimable by someone else.

    Args:
        client: a connected `redis.Redis`.
        stream_key: the stream's key.
        group: the consumer group's name (must already exist -- call
            `ensure_group` first).
        consumer: this reader's consumer name within the group (an
            arbitrary string you choose, e.g. "c1"). Consumer names are
            created implicitly by Redis the first time they're used.
        count: max number of entries to return. May return fewer (including
            zero, if the stream has no new entries right now).

    Returns:
        A list of `(entry_id, fields)` tuples, in stream order, where
        `entry_id` is the stream ID string (e.g. `"1690000000000-0"`) and
        `fields` is the entry's field dict, i.e. `{"payload": "<json
        string>"}`. Empty list if there is nothing new to read. (Hint:
        redis-py's `xreadgroup` return shape already nests things this way
        per-stream -- look at what it hands back before reshaping it
        yourself.)
    """
    raise NotImplementedError


def ack(client, stream_key, group, entry_ids):
    """Acknowledge the given entries for `group`, via `XACK`.

    Acking an entry removes it from the group's PEL -- it is done, for
    good, regardless of which consumer originally read it or which consumer
    (after a reclaim) actually finished it. There is no concept of "commit
    an offset covering everything up to here": each entry is retired
    individually, which is why an at-least-once Streams consumer must ack
    every entry it successfully finishes, not just periodically checkpoint
    a position.

    Args:
        client: a connected `redis.Redis`.
        stream_key: the stream's key.
        group: the consumer group's name.
        entry_ids: a list of entry ID strings to ack (as returned by
            `consume_new` / `reclaim`). May be empty.

    Returns:
        The number of entries actually acked (an int, as `XACK` reports --
        acking an ID that isn't pending, e.g. already acked, doesn't count
        again and doesn't error).
    """
    raise NotImplementedError


def reclaim(client, stream_key, group, consumer, min_idle_ms, count):
    """Steal up to `count` pending entries older than `min_idle_ms` (from
    ANY consumer in `group`, not just a specific one) and reassign them to
    `consumer`, via `XAUTOCLAIM`.

    This is the recovery mechanism for a dead consumer. Some other consumer
    read entries via `consume_new` (putting them in the PEL under its own
    name) and then stopped responding -- crashed, got killed, network
    partition, whatever -- without acking. Those entries do not disappear;
    they sit in the PEL attributed to a consumer that will never finish
    them, unless something takes over. `XAUTOCLAIM` scans the PEL for
    entries idle (time since last delivery) at least `min_idle_ms`,
    reassigns up to `count` of them to `consumer` (bumping their idle time
    and delivery count), and returns them ready to process -- as far as
    Redis is concerned they are now `consumer`'s pending work, exactly as if
    `consumer` had just read them fresh. Prefer `XAUTOCLAIM` over the older
    `XPENDING` + `XCLAIM` pair (it does both steps -- "find idle candidates"
    and "claim them" -- in one round trip and handles paging via its cursor
    for you); an `XPENDING`-then-`XCLAIM` implementation is also acceptable
    if you want to see the two steps split apart.

    A `min_idle_ms` of `0` claims regardless of how recently the entry was
    delivered (useful for tests that don't want to wait); in production
    you'd pick something comfortably larger than your worker's expected
    processing time, so you don't steal work from a consumer that's simply
    still busy with it.

    Args:
        client: a connected `redis.Redis`.
        stream_key: the stream's key.
        group: the consumer group's name.
        consumer: the name of the (alive) consumer to reassign entries to.
        min_idle_ms: minimum idle time, in milliseconds, an entry must have
            before it's eligible to be claimed.
        count: max number of entries to claim in this call.

    Returns:
        A list of `(entry_id, fields)` tuples for the entries claimed, same
        shape as `consume_new`'s return value -- they are now pending under
        `consumer` and still need to be acked once processed. Empty list if
        nothing was eligible to claim.
    """
    raise NotImplementedError
