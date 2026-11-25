"""CP1 validator for the s10 capstone -- STEADY convergence.

Loads the FULL event stream (all events in data/events.json), each enriched
with its real catalog `category` joined in from data/products.json (the raw
event doesn't carry category -- see .authoring/design.md), pushes it onto a
Redis Stream via the learner's `produce`, drains it completely with two
consumers in the same group (proving the group, not just a single reader,
does the work), and checks the resulting `t08_state` materialization in
MongoDB against data/ground-truth.json's `current_state`: `count` exact,
`price_sum` within a small float tolerance, `per_category_count` exact per
category.

No crash, no reclaim here -- this is the base case: at-least-once delivery
over a healthy run should already converge to the correct current-state view.
CP2 is the harder claim (convergence survives a crash).

Run from this task's directory:

    uv run python tests/validate_cp1.py
"""

import json
import sys
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


def _load_enriched_events():
    """Every event from data/events.json, each with its real catalog
    `category` joined in from data/products.json -- events are coupled to
    the catalog by product_id, but the raw event schema itself has no
    category field (see .authoring/design.md)."""
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

    client = redis_client()
    redis_flush_prefix(client, REDIS_PREFIX)

    db = mongo_db()
    db.drop_collection(STATE_COLLECTION)

    events = _load_enriched_events()
    n = len(events)

    pipeline.ensure_group(client, STREAM_KEY, GROUP)
    pipeline.produce(client, STREAM_KEY, events)

    # Two consumers in the SAME group -- not just one reader -- so a
    # single-consumer shortcut can't hide a group-membership bug.
    split = n // 2
    processed_c1 = pipeline.run_consumer(client, db, STREAM_KEY, GROUP, "c1", max_messages=split)
    processed_c2 = pipeline.run_consumer(client, db, STREAM_KEY, GROUP, "c2")
    processed = processed_c1 + processed_c2

    if processed != n:
        not_passed(
            f"consumers processed {processed} messages total (c1={processed_c1}, "
            f"c2={processed_c2}), expected {n} (the full event stream) -- the "
            "drain did not reach the end of the stream"
        )

    pending_summary = client.xpending(STREAM_KEY, GROUP)
    n_pending = pending_summary["pending"] if pending_summary else 0
    if n_pending != 0:
        not_passed(f"{n_pending} entries still pending (unacked) after a full drain")

    state = pipeline.current_state_summary(db)
    _assert_state_matches(state, expected)

    passed(
        f"current_state converged over {n} events: count={state['count']} "
        f"price_sum={state['price_sum']} (ground truth count={expected['count']} "
        f"price_sum={expected['price_sum']})"
    )


if __name__ == "__main__":
    main()
