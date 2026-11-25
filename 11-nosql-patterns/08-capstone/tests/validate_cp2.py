"""CP2 validator for the s10 capstone -- CHAOS: crash + reclaim convergence.

This is the headline result of the capstone: at-least-once delivery
(Redis Streams consumer groups) plus an idempotent, watermarked materialize
equals effectively-once STATE, even across a consumer crash that leaves real
entries sitting in the group's Pending Entries List (PEL), owned by a
consumer that never comes back.

Setup is identical to CP1 (same full, category-enriched event stream), but
the drain is deliberately broken into three ranges, by POSITION in the
stream (which is produce/event_id order, not chronological order -- see
.authoring/design.md, events are shuffled so scraped_at does not correlate
with event_id):

  * batch A (first 50%) -- consumer "c1" reads, materializes, and ACKs these
    normally, via `run_consumer(..., max_messages=len(A))`. This is
    real, completed work.
  * batch B (next 20%) -- "c1" reads these via a RAW `XREADGROUP` call made
    directly by this validator (not through `run_consumer`), which delivers
    them into c1's pending list, but this validator deliberately never calls
    `materialize`/`XACK` on them. This is the crash: c1 died after the read
    landed the entries in its PEL but before it got to process them. They
    sit there, genuinely pending, genuinely unprocessed, attributed to a
    consumer that will never ack them.
  * batch C (final 30%) -- never read by anyone until after the reclaim
    below; still ordinary un-delivered ('>') backlog.

  A fresh consumer "c2" then: (1) calls `reclaim_and_run(..., min_idle_ms=
  small)` to steal and finish batch B via XAUTOCLAIM, and (2) calls
  `run_consumer` to drain batch C. The final `current_state_summary` must
  STILL match ground truth EXACTLY, and XPENDING must be 0 -- proving the
  crash didn't lose or corrupt anything.

WHY THIS ISN'T A WEAK TEST (the "would a naive implementation pass by luck"
concern): it would be easy to accidentally write a crash scenario where a
non-idempotent, non-watermarked materialize (e.g. a plain "upsert, whichever
arrives last wins" or worse, "skip if this product_id already has a
document") still happens to reach the right final numbers, just because the
reclaimed batch happens not to interact with anything else. We rule that out
by computing, from the ACTUAL event corpus (deterministic, no randomness),
how many products have a batch-B (reclaimed) observation that is CHRONOLOG-
ICALLY NEWER than what batch A already wrote for that same product (proving
reclaim must genuinely OVERWRITE, not no-op on "already exists"), and how
many products have a batch-C observation that is newer still than whatever
reclaim just wrote (proving the forward drain after reclaim must overwrite
the just-reclaimed value too, not treat the product as "settled"). Both
counts are asserted well above a floor before the pipeline even runs, so this
checkpoint is a genuine stress test of watermark comparison, not a coincidence
of a lucky split. See `_crash_injection_strength` below.

Run from this task's directory:

    uv run python tests/validate_cp2.py
"""

import json
import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT / "src"))

from harness.common import (  # noqa: E402
    EVENTS_PATH,
    PRODUCTS_PATH,
    guarded,
    load_ground_truth,
    mongo_db,
    not_passed,
    passed,
    redis_client,
    redis_flush_prefix,
)

import pipeline  # noqa: E402

REDIS_PREFIX = "s10:t08:"
STREAM_KEY = "s10:t08:events"
GROUP = "s10:t08:materializers"
STATE_COLLECTION = "t08_state"

PRICE_SUM_TOLERANCE = 0.02

A_FRACTION = 0.5   # completed normally before the crash
B_FRACTION = 0.7   # cumulative -- batch B is [A_FRACTION, B_FRACTION)

MIN_IDLE_MS = 10
IDLE_SLEEP_SECONDS = 0.1  # comfortably clears MIN_IDLE_MS before reclaiming

# Empirically measured against the committed data/events.json (deterministic,
# fixed seeds -- see .authoring/design.md): at the 50%/70% split used below,
# 321 products have a batch-B observation newer than their batch-A one, and
# 490 products have a batch-C observation newer than whatever's true after
# batch B. Floors are set well under those so the assertion is a sanity check
# on the corpus/split, not a brittle exact-count match.
MIN_RECLAIM_OVERWRITES = 100
MIN_POST_RECLAIM_OVERWRITES = 100


def _load_enriched_events():
    categories = {}
    with PRODUCTS_PATH.open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            categories[p["product_id"]] = p["category"]

    events = []
    with EVENTS_PATH.open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            e["category"] = categories[e["product_id"]]
            events.append(e)
    return events


def _crash_injection_strength(events, a_end, b_end):
    """How many products get a genuine out-of-order overwrite across the
    crash boundary -- see the module docstring above. Pure Python over the
    in-memory event list, no DB/Redis involved."""

    def watermark(e):
        return (e["scraped_at"], e["event_id"])

    state_after_a = {}
    for e in events[:a_end]:
        pid = e["product_id"]
        wm = watermark(e)
        if pid not in state_after_a or wm > state_after_a[pid]:
            state_after_a[pid] = wm

    reclaim_overwrites = 0
    state_after_b = dict(state_after_a)
    for e in events[a_end:b_end]:
        pid = e["product_id"]
        wm = watermark(e)
        if pid in state_after_a and wm > state_after_a[pid]:
            reclaim_overwrites += 1
        if pid not in state_after_b or wm > state_after_b[pid]:
            state_after_b[pid] = wm

    post_reclaim_overwrites = 0
    for e in events[b_end:]:
        pid = e["product_id"]
        wm = watermark(e)
        if pid in state_after_b and wm > state_after_b[pid]:
            post_reclaim_overwrites += 1

    return reclaim_overwrites, post_reclaim_overwrites


def _assert_state_matches(state, expected):
    if not isinstance(state, dict):
        not_passed(f"current_state_summary() returned {state!r}, expected a dict")

    if state.get("count") != expected["count"]:
        not_passed(
            f"current_state_summary()['count']={state.get('count')}, expected "
            f"{expected['count']} exactly"
        )

    price_sum = state.get("price_sum")
    if not isinstance(price_sum, (int, float)):
        not_passed(f"current_state_summary()['price_sum']={price_sum!r}, expected a number")
    if abs(float(price_sum) - expected["price_sum"]) > PRICE_SUM_TOLERANCE:
        not_passed(
            f"current_state_summary()['price_sum']={price_sum}, expected "
            f"{expected['price_sum']} within {PRICE_SUM_TOLERANCE}"
        )

    got_cat = state.get("per_category_count") or {}
    exp_cat = expected["per_category_count"]
    missing = [c for c in exp_cat if c not in got_cat]
    if missing:
        not_passed(f"per_category_count missing categories: {missing}")
    extra = [c for c in got_cat if c not in exp_cat]
    if extra:
        not_passed(f"per_category_count has unexpected categories: {extra}")
    for cat, exp_count in exp_cat.items():
        if got_cat[cat] != exp_count:
            not_passed(
                f"per_category_count[{cat!r}]={got_cat[cat]}, expected {exp_count} exactly"
            )


@guarded
def main():
    gt = load_ground_truth()
    expected = gt["current_state"]

    events = _load_enriched_events()
    n = len(events)
    a_end = int(n * A_FRACTION)
    b_end = int(n * B_FRACTION)
    crash_count = b_end - a_end
    tail_count = n - b_end

    reclaim_overwrites, post_reclaim_overwrites = _crash_injection_strength(events, a_end, b_end)
    if reclaim_overwrites < MIN_RECLAIM_OVERWRITES:
        not_passed(
            f"crash injection too weak: only {reclaim_overwrites} products have a "
            f"batch-B observation newer than batch-A's, expected >= "
            f"{MIN_RECLAIM_OVERWRITES} -- adjust A_FRACTION/B_FRACTION"
        )
    if post_reclaim_overwrites < MIN_POST_RECLAIM_OVERWRITES:
        not_passed(
            f"crash injection too weak: only {post_reclaim_overwrites} products have a "
            f"batch-C observation newer than batch-B's, expected >= "
            f"{MIN_POST_RECLAIM_OVERWRITES} -- adjust A_FRACTION/B_FRACTION"
        )

    client = redis_client()
    redis_flush_prefix(client, REDIS_PREFIX)

    db = mongo_db()
    db.drop_collection(STATE_COLLECTION)

    pipeline.ensure_group(client, STREAM_KEY, GROUP)
    pipeline.produce(client, STREAM_KEY, events)

    # Batch A: c1 does real, completed work.
    processed_a = pipeline.run_consumer(client, db, STREAM_KEY, GROUP, "c1", max_messages=a_end)
    if processed_a != a_end:
        not_passed(f"c1 processed {processed_a} messages before the crash point, expected {a_end}")

    # Batch B: simulate the crash. Raw XREADGROUP (not run_consumer) delivers
    # these into c1's pending list; deliberately no materialize/XACK. c1 is
    # now "dead" -- these entries are genuinely pending, forever, from c1's
    # point of view.
    resp = client.xreadgroup(GROUP, "c1", {STREAM_KEY: ">"}, count=crash_count)
    crashed_entries = resp[0][1] if resp else []
    if len(crashed_entries) != crash_count:
        not_passed(
            f"crash simulation delivered {len(crashed_entries)} entries to c1's PEL, "
            f"expected {crash_count}"
        )

    pending_summary = client.xpending(STREAM_KEY, GROUP)
    n_pending = pending_summary["pending"] if pending_summary else 0
    if n_pending != crash_count:
        not_passed(
            f"{n_pending} entries pending right after the simulated crash, expected "
            f"exactly {crash_count} (batch B, all owned by the dead consumer c1)"
        )

    time.sleep(IDLE_SLEEP_SECONDS)

    # A fresh consumer reclaims c1's abandoned pending entries.
    reclaimed = pipeline.reclaim_and_run(client, db, STREAM_KEY, GROUP, "c2", MIN_IDLE_MS)
    if reclaimed != crash_count:
        not_passed(f"reclaim_and_run() reclaimed {reclaimed} entries, expected {crash_count}")

    pending_after_reclaim = client.xpending(STREAM_KEY, GROUP)
    n_pending_after_reclaim = pending_after_reclaim["pending"] if pending_after_reclaim else 0
    if n_pending_after_reclaim != 0:
        not_passed(
            f"{n_pending_after_reclaim} entries still pending after reclaim_and_run() -- "
            "expected 0 (everything reclaimed must get materialized and acked)"
        )

    # c2 drains the remaining, never-yet-read backlog (batch C).
    processed_tail = pipeline.run_consumer(client, db, STREAM_KEY, GROUP, "c2")
    if processed_tail != tail_count:
        not_passed(
            f"c2 drained {processed_tail} messages after reclaim, expected {tail_count} "
            "(the remaining un-delivered backlog)"
        )

    total_processed = processed_a + reclaimed + processed_tail
    if total_processed != n:
        not_passed(
            f"accounted for {total_processed} messages total (a={processed_a}, "
            f"reclaimed={reclaimed}, tail={processed_tail}), expected {n}"
        )

    final_pending = client.xpending(STREAM_KEY, GROUP)
    n_final_pending = final_pending["pending"] if final_pending else 0
    if n_final_pending != 0:
        not_passed(f"{n_final_pending} entries still pending at the end of the run, expected 0")

    state = pipeline.current_state_summary(db)
    _assert_state_matches(state, expected)

    passed(
        f"survived crash+reclaim ({crash_count} reclaimed, {reclaim_overwrites} genuine "
        f"reclaim overwrites, {post_reclaim_overwrites} genuine post-reclaim overwrites): "
        f"count={state['count']} price_sum={state['price_sum']} matches ground truth; "
        "XPENDING=0"
    )


if __name__ == "__main__":
    main()
