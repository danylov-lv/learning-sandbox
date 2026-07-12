"""Validator for 10-nosql-patterns task 04 -- redis-streams-consumer.

Simulates a worker pool draining a price-update stream through a Redis
Streams consumer group, and checks the properties that make it an
at-least-once queue with crash recovery, not just a fancier list:

  1. A consumer ("c1") reads a batch via `consume_new` and then "dies"
     without acking -- we simply never call `ack` for it, which is exactly
     what a crash looks like from Redis's point of view: the entries stay
     in the Pending Entries List (PEL), attributed to c1, forever, unless
     someone reclaims them.
  2. A second consumer ("c2") calls `reclaim` with `min_idle_ms=0` and must
     get ALL of c1's stranded entries back (steal-from-any-consumer, not
     just its own). It processes and acks them, then drains the rest of
     the stream normally.
  3. No loss: the set of distinct `event_id`s processed (from c1's
     initial batch via reclaim, plus everything c2 reads directly) equals
     the full set of produced event_ids. At-least-once, not lossy.
  4. PEL mechanics, checked explicitly: right after `consume_new` (before
     any ack), the read entries appear in `XPENDING`. Right after `ack`,
     they no longer do. At the very end, once everything has been
     processed and acked, `XPENDING`'s summary shows zero pending.

Run from this task's directory:

    uv run python tests/validate.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    EVENTS_PATH,
    guarded,
    not_passed,
    passed,
    redis_client,
    redis_flush_prefix,
)
from src.consumer import ack, consume_new, ensure_group, produce, reclaim  # noqa: E402

NAMESPACE = "s10:t04:"
STREAM_KEY = NAMESPACE + "stream"
GROUP = NAMESPACE + "workers"

N_EVENTS = 2000
BATCH = 500


def _load_events(n):
    if not EVENTS_PATH.exists():
        not_passed(f"events data not found at {EVENTS_PATH} -- run `uv run python generate.py` first")
    events = []
    with EVENTS_PATH.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            events.append(json.loads(line))
    if len(events) < n:
        not_passed(f"expected at least {n} events in {EVENTS_PATH}, found {len(events)}")
    return events


def _event_id_of(entry_id, fields):
    if "payload" not in fields:
        not_passed(f"stream entry {entry_id} is missing the 'payload' field: {fields!r}")
    try:
        return json.loads(fields["payload"])["event_id"]
    except (TypeError, ValueError, KeyError) as e:
        not_passed(f"stream entry {entry_id}'s payload is not the expected JSON event: {e}")


def _pending_ids(client):
    return {
        row["message_id"]
        for row in client.xpending_range(STREAM_KEY, GROUP, min="-", max="+", count=1_000_000)
    }


@guarded
def main():
    client = redis_client()
    redis_flush_prefix(client, NAMESPACE)
    ensure_group(client, STREAM_KEY, GROUP)

    events = _load_events(N_EVENTS)
    expected_event_ids = {e["event_id"] for e in events}

    produce(client, STREAM_KEY, events)
    stream_len = client.xlen(STREAM_KEY)
    if stream_len != N_EVENTS:
        not_passed(f"produce() left {stream_len} entries on the stream, expected {N_EVENTS}")

    processed_event_ids = set()

    # --- c1 reads a batch, then "dies" (never acks) ----------------------
    c1_batch = consume_new(client, STREAM_KEY, GROUP, "c1", BATCH)
    if len(c1_batch) != BATCH:
        not_passed(f"consume_new(c1) returned {len(c1_batch)} entries, expected {BATCH}")
    c1_ids = [entry_id for entry_id, _ in c1_batch]

    # PEL mechanic, part 1: unacked entries must show up as pending.
    pending_after_read = _pending_ids(client)
    missing_from_pel = set(c1_ids) - pending_after_read
    if missing_from_pel:
        not_passed(
            f"consume_new delivered {len(c1_ids)} entries to c1 but XPENDING does "
            f"not list them as pending (e.g. {next(iter(missing_from_pel))}) -- "
            "XREADGROUP must record delivered-but-unacked entries in the PEL"
        )

    # --- c2 reclaims c1's stranded work (simulating c1's crash) ----------
    reclaimed = reclaim(client, STREAM_KEY, GROUP, "c2", min_idle_ms=0, count=BATCH * 2)
    reclaimed_ids = {entry_id for entry_id, _ in reclaimed}
    missing_reclaim = set(c1_ids) - reclaimed_ids
    if missing_reclaim:
        not_passed(
            f"reclaim() did not recover all of c1's un-acked entries -- c1 had "
            f"{len(c1_ids)} pending, reclaim() returned {len(reclaimed)}, missing "
            f"e.g. {next(iter(missing_reclaim))}"
        )

    for entry_id, fields in reclaimed:
        processed_event_ids.add(_event_id_of(entry_id, fields))

    acked = ack(client, STREAM_KEY, GROUP, list(reclaimed_ids))
    if acked != len(reclaimed_ids):
        not_passed(f"ack() reported {acked} acked, expected {len(reclaimed_ids)}")

    # PEL mechanic, part 2: an acked entry must no longer be pending, and a
    # read-but-unacked entry (there shouldn't be any left from c1 now, but
    # prove the general shape) is what reclaim() just demonstrated above.
    pending_after_ack = _pending_ids(client)
    still_pending = reclaimed_ids & pending_after_ack
    if still_pending:
        not_passed(
            f"{len(still_pending)} entries were acked but still appear in XPENDING "
            f"(e.g. {next(iter(still_pending))}) -- XACK must remove them from the PEL"
        )

    # --- c2 drains everything else normally -------------------------------
    while True:
        batch = consume_new(client, STREAM_KEY, GROUP, "c2", BATCH)
        if not batch:
            break
        ids = [entry_id for entry_id, _ in batch]
        for entry_id, fields in batch:
            processed_event_ids.add(_event_id_of(entry_id, fields))
        n_acked = ack(client, STREAM_KEY, GROUP, ids)
        if n_acked != len(ids):
            not_passed(f"ack() reported {n_acked} acked, expected {len(ids)} for a fresh batch")

    # --- No loss: at-least-once over the full produced set ----------------
    missing = expected_event_ids - processed_event_ids
    if missing:
        not_passed(
            f"{len(missing)} produced events were never processed (at-least-once "
            f"violated), e.g. event_id={next(iter(missing))}"
        )
    unexpected = processed_event_ids - expected_event_ids
    if unexpected:
        not_passed(
            f"processed {len(unexpected)} event_id(s) that were never produced, "
            f"e.g. {next(iter(unexpected))} -- check payload encoding/decoding"
        )

    # --- PEL fully drained --------------------------------------------------
    summary = client.xpending(STREAM_KEY, GROUP)
    if summary["pending"] != 0:
        not_passed(
            f"expected 0 pending entries once everything is processed, XPENDING "
            f"summary shows {summary['pending']}"
        )

    redis_flush_prefix(client, NAMESPACE)
    passed(
        f"{len(processed_event_ids)}/{len(expected_event_ids)} events processed "
        f"at-least-once; c1's {len(c1_ids)} stranded pending entries reclaimed and "
        "finished by c2; PEL fully drained"
    )


if __name__ == "__main__":
    main()
