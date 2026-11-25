"""Scaffold for task 05 — event-time windowed aggregation.

Run this as a standalone process, host-side:

    uv run python src/consumer.py

It consumes topic `s07.t05.price-updates` (group `t05-consumer`) from the
beginning, and for every event it must:

  1. Parse `event_ts` (ISO 8601, UTC, millisecond precision, e.g.
     "2025-07-01T00:37:12.123Z").
  2. Floor that timestamp to its 15-minute TUMBLING window start — the
     window boundary is anchored at the corpus start, 2025-07-01T00:00:00Z,
     so window starts are 00:00, 00:15, 00:30, ... 01:45.
  3. UPSERT into mart.t05_window_category: increment `cnt` by 1 and
     `price_sum` by the event's price, for the (window_start, category) key.

The stream's publish order (Kafka offset / seq) is monotonic, but roughly 2%
of events are "late": their `event_ts` was pushed 1-15 minutes EARLIER than
where they sit in the log. Windowing by offset or arrival order puts those
events in the wrong bucket. Windowing by `event_ts` puts them where they
belong. That distinction is the entire point of this task — see the README.

The process should run until the topic goes idle for about 10 seconds (no
new messages), then commit whatever remains, close cleanly, and exit 0.
Rerunning it from scratch (with the mart table dropped, or with a fresh
consumer group) must reproduce the same aggregates — the upsert makes a
partial or repeated run safe.

The DDL and a small DB helper are provided below; you write the window
flooring and the upsert.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from confluent_kafka import Consumer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.common import kafka_bootstrap, pg_connect  # noqa: E402

TOPIC = "s07.t05.price-updates"
GROUP_ID = "t05-consumer"

WINDOW_START = datetime(2025, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_SIZE = timedelta(minutes=15)

IDLE_TIMEOUT_S = 10.0
POLL_TIMEOUT_S = 1.0

DDL = """
CREATE TABLE IF NOT EXISTS mart.t05_window_category (
    window_start TIMESTAMPTZ NOT NULL,
    category TEXT NOT NULL,
    cnt BIGINT NOT NULL,
    price_sum NUMERIC NOT NULL,
    PRIMARY KEY (window_start, category)
);
"""


def ensure_table():
    conn = pg_connect()
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    conn.close()


def window_start_for(event_ts):
    """Given an event's event_ts (ISO 8601 UTC string, e.g.
    "2025-07-01T00:37:12.123Z"), return the datetime marking the start of
    its 15-minute tumbling window.

    TODO:
    - Parse event_ts into a timezone-aware UTC datetime. Python's
      datetime.fromisoformat() does not accept a trailing "Z" before 3.11 —
      check what your interpreter needs (replace "Z" with "+00:00", or use
      fromisoformat directly if it already handles it).
    - Floor to the window: how many whole WINDOW_SIZE periods have elapsed
      since WINDOW_START? Integer-divide that elapsed duration by
      WINDOW_SIZE, then multiply back — this is the same "floor division"
      trick as bucketing an offset into a page, applied to a timedelta.
    - Return WINDOW_START + (that many windows) * WINDOW_SIZE.

    Get this function right and the late-event handling falls out for free:
    you are windowing by event_ts here, never by the order events arrive in.
    """
    raise NotImplementedError


def upsert(conn, window_start, category, price):
    """Increment (cnt, price_sum) for (window_start, category) by (1, price).

    TODO:
    - One row per (window_start, category): INSERT ... ON CONFLICT
      (window_start, category) DO UPDATE, incrementing cnt and price_sum in
      the same statement (don't SELECT-then-UPDATE — that's a race even
      single-threaded across process restarts, and it's slower).
    - Use conn.cursor() + conn.commit() explicitly. Do NOT rely on
      `with conn:` to manage the transaction here — on this psycopg version
      `with conn:` closes the connection on exit, not just the transaction.
    - Batch commits (e.g. every N rows, or once per poll-loop idle check)
      rather than committing every single message — 200k events is enough
      to make per-message commits noticeably slow.
    """
    raise NotImplementedError


def main():
    ensure_table()

    # TODO: build the Consumer (bootstrap.servers, group.id=GROUP_ID,
    # auto.offset.reset="earliest" so a fresh group reads from the start),
    # subscribe to [TOPIC].
    #
    # TODO: poll loop. Each message: json-decode the value, compute
    # window_start_for(event["event_ts"]), upsert(conn, window_start,
    # event["category"], event["price"]). Track how long it's been since the
    # last real message; once that exceeds IDLE_TIMEOUT_S, commit, close the
    # consumer, and exit 0 — there is no natural "end of stream" signal from
    # Kafka itself, so idle-timeout is the termination condition here.

    raise NotImplementedError


if __name__ == "__main__":
    main()
