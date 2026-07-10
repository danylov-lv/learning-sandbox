"""Validator for 07-streaming task 04 -- exactly-once-into-postgres.

Produces the FULL corpus onto s07.t04.price-updates, drops the graded
result table for a clean slate, then drives the learner's consumer through
TWO injected mid-stream crashes and a final clean run to completion. Checks
that core.t04_category_totals matches the ground-truth per-category totals
EXACTLY -- not approximately -- proving the aggregate survived redelivery
without double-counting or losing anything.

Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    create_topic,
    guarded,
    iter_events,
    load_ground_truth,
    not_passed,
    passed,
    pg_connect,
    produce_events,
    reset_topics,
)

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

TOPIC = "s07.t04.price-updates"
CONSUMER_SCRIPT = TASK_ROOT / "src" / "consumer.py"
CRASH_AFTER_1 = 50000
CRASH_AFTER_2 = 130000
CRASH_RUN_TIMEOUT = 300
FULL_RUN_TIMEOUT = 300
PRICE_TOLERANCE = 0.05
PRICE_SUM_TOTAL_TOLERANCE = 0.10


def _drop_result_state(conn):
    """Force a clean slate for the graded table. Also defensively drop the
    two most likely names a learner would pick for their private dedup /
    offset-storage table, so a stale table from a previous attempt at this
    task can't quietly make the run look correct for the wrong reason. We
    deliberately do NOT know (and should not need to know) the learner's
    actual private table name beyond these common candidates -- a
    resumable consumer must in any case tolerate a fresh start with none
    of its own state present."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS core")
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
    cur.execute("DROP TABLE IF EXISTS core.t04_category_totals")
    cur.execute("DROP TABLE IF EXISTS ops.t04_offsets, ops.t04_seen CASCADE")
    conn.commit()


def _read_totals(conn):
    cur = conn.cursor()
    cur.execute("SELECT category, cnt, price_sum FROM core.t04_category_totals")
    return {row[0]: {"cnt": row[1], "price_sum": float(row[2])} for row in cur.fetchall()}


def _run_consumer(env_overrides, timeout):
    env = os.environ.copy()
    env.pop("S07_CRASH_AFTER", None)
    env.update(env_overrides)
    try:
        return subprocess.run(
            ["uv", "run", "python", str(CONSUMER_SCRIPT)],
            cwd=str(TASK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


@guarded
def main():
    if not CONSUMER_SCRIPT.exists():
        not_passed(f"src/consumer.py not found at {CONSUMER_SCRIPT}")

    gt = load_ground_truth()
    per_category = gt["per_category_totals"]
    total_events = gt["total_events"]
    price_sum_all = gt["price_sum_all"]

    reset_topics("s07.t04.")
    create_topic(TOPIC, partitions=6)

    conn = pg_connect()
    try:
        _drop_result_state(conn)
    finally:
        conn.close()

    corpus = list(iter_events())
    if len(corpus) != total_events:
        not_passed(
            f"data/events.ndjson has {len(corpus)} lines, ground truth total_events is "
            f"{total_events} -- regenerate the corpus first"
        )

    produced = produce_events(TOPIC, corpus, key_field="product_id")
    if produced != total_events:
        not_passed(f"produced {produced} events to {TOPIC}, expected {total_events}")

    # --- crash run 1: kill mid-stream. Nonzero exit expected and tolerated.
    r1 = _run_consumer({"S07_CRASH_AFTER": str(CRASH_AFTER_1)}, CRASH_RUN_TIMEOUT)
    if r1 is None:
        not_passed(
            f"first crash run (S07_CRASH_AFTER={CRASH_AFTER_1}) did not exit within "
            f"{CRASH_RUN_TIMEOUT}s -- the crash hook should hard-exit almost immediately "
            "once it reaches the count"
        )
    if r1.returncode == 0:
        tail = (r1.stdout or "")[-1000:] + (r1.stderr or "")[-1000:]
        not_passed(
            f"first crash run (S07_CRASH_AFTER={CRASH_AFTER_1}) exited 0 -- expected a nonzero "
            f"exit from the injected os._exit(1) crash hook; is the consumer calling "
            f"_maybe_crash? output tail:\n{tail}"
        )

    # --- crash run 2: kill mid-stream again, further in. Nonzero exit expected.
    r2 = _run_consumer({"S07_CRASH_AFTER": str(CRASH_AFTER_2)}, CRASH_RUN_TIMEOUT)
    if r2 is None:
        not_passed(
            f"second crash run (S07_CRASH_AFTER={CRASH_AFTER_2}) did not exit within "
            f"{CRASH_RUN_TIMEOUT}s"
        )
    if r2.returncode == 0:
        tail = (r2.stdout or "")[-1000:] + (r2.stderr or "")[-1000:]
        not_passed(
            f"second crash run (S07_CRASH_AFTER={CRASH_AFTER_2}) exited 0 -- expected a "
            f"nonzero exit from the injected crash hook; output tail:\n{tail}"
        )

    # --- clean run: no crash env, must catch up and exit 0.
    r3 = _run_consumer({}, FULL_RUN_TIMEOUT)
    if r3 is None:
        not_passed(
            f"final clean run did not exit within {FULL_RUN_TIMEOUT}s -- did it fail to reach "
            "idle-exit and catch up with the topic?"
        )
    if r3.returncode != 0:
        tail = (r3.stdout or "")[-1500:] + (r3.stderr or "")[-1500:]
        not_passed(f"final clean run exited {r3.returncode} -- output tail:\n{tail}")

    conn = pg_connect()
    try:
        try:
            totals = _read_totals(conn)
        except Exception as e:
            not_passed(
                f"could not read core.t04_category_totals after the runs -- does it exist? {e}"
            )
    finally:
        conn.close()

    if not totals:
        not_passed(
            "core.t04_category_totals is empty after all three runs -- consumer never wrote "
            "any aggregate rows"
        )

    expected_categories = set(per_category.keys())
    actual_categories = set(totals.keys())
    missing = expected_categories - actual_categories
    extra = actual_categories - expected_categories
    if missing:
        not_passed(f"core.t04_category_totals is missing categories: {sorted(missing)}")
    if extra:
        not_passed(f"core.t04_category_totals has unexpected extra categories: {sorted(extra)}")

    for category, expected in per_category.items():
        actual = totals[category]
        expected_cnt = expected["count"]
        expected_price_sum = expected["price_sum"]
        if actual["cnt"] != expected_cnt:
            direction = "over" if actual["cnt"] > expected_cnt else "under"
            hint = (
                " (double-counting across crash-induced redelivery?)"
                if direction == "over"
                else " (lost updates across a crash?)"
            )
            not_passed(
                f"category {category!r} counted {actual['cnt']}, expected {expected_cnt}"
                f"{hint}"
            )
        if abs(actual["price_sum"] - expected_price_sum) > PRICE_TOLERANCE:
            not_passed(
                f"category {category!r} price_sum {actual['price_sum']}, expected "
                f"{expected_price_sum} (tolerance {PRICE_TOLERANCE})"
            )

    total_cnt = sum(v["cnt"] for v in totals.values())
    total_price_sum = sum(v["price_sum"] for v in totals.values())
    if total_cnt != total_events:
        not_passed(
            f"sum of cnt across categories is {total_cnt}, expected total_events={total_events}"
        )
    if abs(total_price_sum - price_sum_all) > PRICE_SUM_TOTAL_TOLERANCE:
        not_passed(
            f"sum of price_sum across categories is {total_price_sum}, expected "
            f"price_sum_all={price_sum_all} (tolerance {PRICE_SUM_TOTAL_TOLERANCE})"
        )

    passed(
        f"exact match across {len(totals)} categories after two injected crashes "
        f"(at {CRASH_AFTER_1} and {CRASH_AFTER_2} messages): total_cnt={total_cnt} "
        f"(matches total_events), total_price_sum={total_price_sum:.2f} "
        f"(matches price_sum_all={price_sum_all} within {PRICE_SUM_TOTAL_TOLERANCE})"
    )


if __name__ == "__main__":
    main()
