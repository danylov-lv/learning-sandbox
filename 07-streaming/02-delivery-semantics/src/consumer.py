"""s07.t02 consumer -- delivery semantics via manual offset commits.

CLI contract (what the validator relies on):

    uv run python src/consumer.py

Behavior contract:
- Consumer group id is fixed: GROUP_ID below ("t02-consumer").
- Subscribes to topic TOPIC ("s07.t02.price-updates").
- For each message, "processes" it by inserting the event's `seq` into
  ops.t02_seen(seq bigint) -- this is the side effect the validator checks.
- Honors env var S07_CRASH_AFTER: if set, the process hard-exits via
  os._exit(1) right after processing that many messages THIS RUN, without
  committing whatever offset is in flight. See _maybe_crash below -- it is a
  TEST HOOK, already implemented, not something you write or rely on beyond
  calling it in the right spot.
- Exits 0 once it has gone IDLE_EXIT_SECONDS with no new message (caught up
  with the topic) -- this is how the validator knows a run finished.

Try it yourself before running the validator:

    S07_CRASH_AFTER=8000 uv run python src/consumer.py   # crashes partway
    uv run python src/consumer.py                        # resumes, catches up
"""

import json
import os
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kafka_bootstrap, pg_connect  # noqa: E402

TOPIC = "s07.t02.price-updates"
GROUP_ID = "t02-consumer"
IDLE_EXIT_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 1.0

DDL = "CREATE TABLE IF NOT EXISTS ops.t02_seen (seq BIGINT NOT NULL)"


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def record_seen(conn, seq: int) -> None:
    """The 'processing' side effect: record that this event's seq was
    consumed. Deliberately NOT deduplicated -- duplicates are expected and
    fine under at-least-once. The validator counts DISTINCT seq, not rows."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ops.t02_seen (seq) VALUES (%s)", (seq,))
    conn.commit()


def _maybe_crash(processed_count: int) -> None:
    """TEST HOOK -- given, not something to implement.

    If S07_CRASH_AFTER is set, hard-exit the process the instant
    processed_count reaches it, bypassing any offset commit that hasn't
    happened yet. This simulates a crash mid-stream so you can observe, by
    where you call this, which commit placement loses messages and which
    one only duplicates them. Call it once per message, after you've decided
    what "processing" a message means for your commit strategy.
    """
    crash_after = os.environ.get("S07_CRASH_AFTER")
    if crash_after is not None and processed_count == int(crash_after):
        print(f"[crash-hook] hard-exiting after {processed_count} messages", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def main() -> None:
    from confluent_kafka import Consumer

    conn = pg_connect()
    ensure_table(conn)

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        # Short session timeout so a crashed member is evicted from the group
        # quickly -- a restarted consumer would otherwise wait out the default
        # 45s session timeout before the broker reassigns its partitions.
        "session.timeout.ms": 6000,
        "heartbeat.interval.ms": 2000,
    })
    consumer.subscribe([TOPIC])

    processed = 0
    idle_seconds = 0.0

    try:
        while idle_seconds < IDLE_EXIT_SECONDS:
            # TODO: implement the consume loop.
            #
            # Each iteration:
            #   1. msg = consumer.poll(POLL_TIMEOUT_SECONDS)
            #   2. If msg is None: no message arrived within the timeout --
            #      bump idle_seconds by POLL_TIMEOUT_SECONDS and continue.
            #   3. If msg.error(): decide whether to skip it (reset
            #      idle_seconds to 0 either way -- the topic is still alive).
            #   4. Otherwise: reset idle_seconds to 0, decode the value with
            #      json.loads(msg.value()) to get `seq`, then decide the
            #      ORDER of the two things that matter:
            #        - record_seen(conn, seq)   -- the "processing" write
            #        - consumer.commit(msg)     -- the manual offset commit
            #        - _maybe_crash(processed)  -- the crash test hook
            #
            # That order is the entire point of this task:
            #   - commit BEFORE record_seen => at-most-once. A crash between
            #     the commit and the write LOSES the message: on restart the
            #     consumer resumes past an offset whose message was never
            #     recorded.
            #   - commit AFTER record_seen => at-least-once. A crash between
            #     the write and the commit REDELIVERS the message on
            #     restart: it gets processed (and recorded) again, producing
            #     a duplicate seq, never a gap.
            #
            # The graded deliverable is at-least-once: zero permanent loss
            # across the injected crash, duplicates allowed. Increment
            # `processed` once per message and call _maybe_crash(processed)
            # at the point in that order that lets the crash hook actually
            # interrupt you before the commit -- i.e. right after the write.
            raise NotImplementedError
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
