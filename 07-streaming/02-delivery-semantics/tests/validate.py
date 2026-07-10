"""Validator for 07-streaming task 02 -- delivery-semantics.

Produces a deterministic subset of the price-update stream, runs the
learner's consumer with an injected mid-stream crash (S07_CRASH_AFTER),
tolerates the nonzero exit, then runs the consumer again to completion, and
checks that no message was permanently lost across the crash. Duplicates
are expected and fine under at-least-once -- the hard gate is zero loss of
distinct seq.

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
    not_passed,
    passed,
    pg_connect,
    produce_events,
    reset_topics,
)

# Fail fast (instead of hanging for minutes) when the stack is down.
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")

TOPIC = "s07.t02.price-updates"
N = 30000
CRASH_AFTER = 8000
CONSUMER_SCRIPT = TASK_ROOT / "src" / "consumer.py"
CRASH_RUN_TIMEOUT = 120
FULL_RUN_TIMEOUT = 180


def _reset_seen_table(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ops")
        cur.execute("CREATE TABLE IF NOT EXISTS ops.t02_seen (seq BIGINT NOT NULL)")
        cur.execute("TRUNCATE ops.t02_seen")
    conn.commit()


def _seen_stats(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT seq) FROM ops.t02_seen")
        return cur.fetchone()


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

    reset_topics("s07.t02.")
    create_topic(TOPIC, partitions=6)

    conn = pg_connect()
    try:
        _reset_seen_table(conn)
    finally:
        conn.close()

    subset = []
    for event in iter_events():
        if event["seq"] >= N:
            break
        subset.append(event)
    if len(subset) != N:
        not_passed(f"corpus has only {len(subset)} events before seq {N} -- regenerate data first")

    produced = produce_events(TOPIC, subset, key_field="product_id")
    if produced != N:
        not_passed(f"produced {produced} events to {TOPIC}, expected {N}")

    # --- crash run: kill the consumer mid-stream, offset commit for the
    # in-flight message must NOT have happened yet. Nonzero exit expected.
    crash_result = _run_consumer({"S07_CRASH_AFTER": str(CRASH_AFTER)}, CRASH_RUN_TIMEOUT)
    if crash_result is None:
        not_passed(
            f"crash run did not exit within {CRASH_RUN_TIMEOUT}s -- the S07_CRASH_AFTER hook "
            "should hard-exit almost immediately once it reaches the count"
        )
    if crash_result.returncode == 0:
        tail = (crash_result.stdout or "")[-1000:] + (crash_result.stderr or "")[-1000:]
        not_passed(
            "crash run (S07_CRASH_AFTER set) exited 0 -- expected a nonzero exit from the "
            f"injected os._exit(1) crash hook; is the consumer calling _maybe_crash? output tail:\n{tail}"
        )

    # --- resume run: no crash env, must catch up and exit 0.
    full_result = _run_consumer({}, FULL_RUN_TIMEOUT)
    if full_result is None:
        not_passed(f"resume run did not exit within {FULL_RUN_TIMEOUT}s -- did it fail to reach idle-exit?")
    if full_result.returncode != 0:
        tail = (full_result.stdout or "")[-1500:] + (full_result.stderr or "")[-1500:]
        not_passed(f"resume run exited {full_result.returncode} -- output tail:\n{tail}")

    conn = pg_connect()
    try:
        try:
            total, distinct = _seen_stats(conn)
        except Exception as e:
            not_passed(f"could not read ops.t02_seen after the runs: {e}")
    finally:
        conn.close()

    if total == 0:
        not_passed("ops.t02_seen is empty after both runs -- consumer never recorded any events")

    if distinct < N:
        missing = N - distinct
        not_passed(
            f"{missing} messages lost across the crash (distinct seq recorded={distinct}, "
            f"expected {N}) -- committing BEFORE the write is at-most-once and loses messages "
            "on a crash between commit and write; commit must happen AFTER record_seen"
        )
    if distinct > N:
        not_passed(
            f"distinct seq recorded ({distinct}) exceeds the produced set ({N}) -- unexpected "
            "extra data in ops.t02_seen; was it truncated before this run?"
        )

    passed(
        f"zero message loss across the injected crash: {distinct}/{N} distinct seq recorded "
        f"({total} total rows, {total - distinct} redelivered duplicates from at-least-once)"
    )


if __name__ == "__main__":
    main()
